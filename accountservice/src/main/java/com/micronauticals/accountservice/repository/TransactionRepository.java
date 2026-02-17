package com.micronauticals.accountservice.repository;

import com.micronauticals.accountservice.entity.financialdata.Transaction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbTable;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.TableSchema;
import software.amazon.awssdk.enhanced.dynamodb.model.BatchWriteItemEnhancedRequest;
import software.amazon.awssdk.enhanced.dynamodb.model.Page;
import software.amazon.awssdk.enhanced.dynamodb.model.PageIterable;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;
import software.amazon.awssdk.enhanced.dynamodb.model.WriteBatch;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

@Repository
public class TransactionRepository {

    private static final Logger log = LoggerFactory.getLogger(TransactionRepository.class);
    private final DynamoDbEnhancedClient dynamoDbEnhancedClient;
    private final DynamoDbTable<Transaction> transactionTable;
    private final DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private final String tableName;

    @Value("${app.user.id:Prabal864}")
    private String defaultUserId;

    @Value("${aws.dynamodb.batch.concurrency:10}")
    private int concurrencyLevel;

    @Value("${aws.dynamodb.batch.timeout:240000}")
    private long batchTimeoutMs;

    @Autowired
    public TransactionRepository(
            DynamoDbEnhancedClient dynamoDbEnhancedClient,
            @Value("${aws.dynamodb.table.name:Transaction_Account_Service}") String tableName) {
        this.dynamoDbEnhancedClient = dynamoDbEnhancedClient;
        this.tableName = tableName;
        this.transactionTable = dynamoDbEnhancedClient.table(tableName,
                TableSchema.fromBean(Transaction.class));
        log.info("Initialized TransactionRepository with DynamoDB table '{}' at {}, user: {}",
                tableName, LocalDateTime.now().format(formatter), defaultUserId);
    }

    /**
     * Save a single transaction to DynamoDB
     */
    public Transaction save(Transaction transaction) {
        log.info("Saving transaction {} to DynamoDB, user: {}",
                transaction.getTxnId(), defaultUserId);
        transactionTable.putItem(transaction);
        return transaction;
    }

    /**
     * Save multiple transactions to DynamoDB using parallel batch processing with controlled concurrency
     * Uses a thread pool to process batches in parallel with configurable concurrency
     */
    public List<Transaction> saveAll(List<Transaction> transactions) {
        if (transactions == null || transactions.isEmpty()) {
            log.info("No transactions to save, user: {}", defaultUserId);
            return transactions;
        }

        final int batchSize = 25; // DynamoDB BatchWriteItem limit
        final int totalTransactions = transactions.size();
        final int totalBatches = (int) Math.ceil((double) totalTransactions / batchSize);

        log.info("Starting parallel batch save of {} transactions using {} threads, user: {}",
                totalTransactions, concurrencyLevel, defaultUserId);

        // Use a custom thread factory for better naming and tracking
        ThreadFactory threadFactory = new ThreadFactory() {
            private final AtomicInteger threadNumber = new AtomicInteger(1);

            @Override
            public Thread newThread(Runnable r) {
                Thread thread = new Thread(r, "DynamoDbBatchWriter-" + threadNumber.getAndIncrement());
                thread.setDaemon(false); // Non-daemon threads complete even if parent thread is interrupted
                return thread;
            }
        };

        // Create a fixed thread pool with the configured concurrency level
        ExecutorService executor = Executors.newFixedThreadPool(concurrencyLevel, threadFactory);

        // Split transactions into batches of 25 (DynamoDB limit)
        List<List<Transaction>> batches = new ArrayList<>();
        for (int i = 0; i < transactions.size(); i += batchSize) {
            int endIndex = Math.min(i + batchSize, transactions.size());
            batches.add(new ArrayList<>(transactions.subList(i, endIndex)));
        }

        // Track batch completion
        final AtomicInteger successfulBatches = new AtomicInteger(0);
        final AtomicInteger failedBatches = new AtomicInteger(0);
        final CountDownLatch latch = new CountDownLatch(batches.size());

        // Submit each batch as a separate task
        List<Future<?>> futures = new ArrayList<>();
        for (int batchNum = 0; batchNum < batches.size(); batchNum++) {
            final int currentBatchNum = batchNum;
            final List<Transaction> currentBatch = batches.get(batchNum);

            futures.add(executor.submit(() -> {
                try {
                    processBatch(currentBatch, currentBatchNum + 1, totalBatches);
                    successfulBatches.incrementAndGet();
                } catch (Exception e) {
                    failedBatches.incrementAndGet();
                    log.error("Error processing batch {}/{}, user: {}, error: {}",
                            currentBatchNum + 1, totalBatches, defaultUserId, e.getMessage(), e);
                } finally {
                    latch.countDown();
                }
            }));
        }

        try {
            // Wait for all batches to complete with configurable timeout (should be less than async timeout)
            long timeoutSeconds = batchTimeoutMs / 1000;
            boolean completed = latch.await(timeoutSeconds, TimeUnit.SECONDS);
            if (!completed) {
                log.warn("Timeout waiting for batch operations to complete after {} seconds, user: {}",
                        timeoutSeconds, defaultUserId);
            }
        } catch (InterruptedException e) {
            log.error("Thread interrupted while waiting for batch operations, user: {}",
                    defaultUserId, e);
            Thread.currentThread().interrupt();
            throw new RuntimeException("Batch processing interrupted", e);
        } finally {
            // Initiate graceful shutdown
            executor.shutdown();
            try {
                // Wait a bit for tasks to complete
                if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
                    // Force shutdown if still running
                    executor.shutdownNow();
                }
            } catch (InterruptedException e) {
                executor.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }

        log.info("Completed parallel batch processing: {}/{} batches successful, {}/{} batches failed, user: {}",
                successfulBatches.get(), totalBatches, failedBatches.get(), totalBatches, defaultUserId);

        return transactions;
    }

    /**
     * Process a single batch of transactions
     */
    private void processBatch(List<Transaction> batch, int batchNum, int totalBatches) {
        String timestamp = LocalDateTime.now().format(formatter);
        log.info("Processing batch {}/{} with {} items at {}, user: {}",
                batchNum, totalBatches, batch.size(), timestamp, defaultUserId);

        // Create a write batch for this chunk
        WriteBatch.Builder<Transaction> writeBuilder = WriteBatch.builder(Transaction.class)
                .mappedTableResource(transactionTable);

        // Add each transaction to the batch
        for (Transaction txn : batch) {
            writeBuilder.addPutItem(txn);
        }

        // Execute the batch write
        BatchWriteItemEnhancedRequest batchWriteItemEnhancedRequest = BatchWriteItemEnhancedRequest.builder()
                .writeBatches(writeBuilder.build())
                .build();

        dynamoDbEnhancedClient.batchWriteItem(batchWriteItemEnhancedRequest);

        log.info("Successfully completed batch {}/{} with {} items, user: {}",
                batchNum, totalBatches, batch.size(), defaultUserId);
    }

    /**
     * Find a transaction by account number and transaction ID
     */
    public Optional<Transaction> findById(String accountNumber, String transactionId) {
        Key key = Key.builder()
                .partitionValue("ACCOUNT#" + accountNumber)
                .sortValue("TXN#" + transactionId)
                .build();

        log.info("Finding transaction {} for account {}, user: {}",
                transactionId, accountNumber, defaultUserId);

        return Optional.ofNullable(transactionTable.getItem(key));
    }

    /**
     * Find all transactions for a specific account
     */
    public List<Transaction> findByAccountNumber(String accountNumber) {
        QueryConditional queryConditional = QueryConditional
                .keyEqualTo(Key.builder()
                        .partitionValue("ACCOUNT#" + accountNumber)
                        .build());

        log.info("Finding all transactions for account {}, user: {}",
                accountNumber, defaultUserId);

        PageIterable<Transaction> pages = transactionTable.query(queryConditional);

        List<Transaction> transactions = new ArrayList<>();
        pages.items().forEach(transactions::add);
        return transactions;
    }

    /**
     * Find all transactions for a specific consent ID
     */
    public List<Transaction> findByConsentId(String consentId) {
        log.info("Finding transactions for consent {}, user: {}",
                consentId, defaultUserId);

        // We need to do a scan with a filter since we don't have GSI in the entity
        List<Transaction> allTransactions = new ArrayList<>();
        PageIterable<Transaction> pages = transactionTable.scan();

        for (Page<Transaction> page : pages) {
            for (Transaction txn : page.items()) {
                if (consentId.equals(txn.getConsentId())) {
                    allTransactions.add(txn);
                }
            }
        }

        log.info("Found {} transactions for consent {}",
                allTransactions.size(), consentId);
        return allTransactions;
    }

    /**
     * Find all transactions for a specific FiAccount ID
     */
    public List<Transaction> findByFiAccountId(Long fiAccountId) {
        log.info("Finding transactions for FiAccount {}, user: {}",
                fiAccountId, defaultUserId);

        // We need to do a scan with a filter since we don't have GSI in the entity
        List<Transaction> allTransactions = new ArrayList<>();
        PageIterable<Transaction> pages = transactionTable.scan();

        for (Page<Transaction> page : pages) {
            for (Transaction txn : page.items()) {
                if (fiAccountId.equals(txn.getFiAccountId())) {
                    allTransactions.add(txn);
                }
            }
        }

        log.info("Found {} transactions for FiAccount {}",
                allTransactions.size(), fiAccountId);
        return allTransactions;
    }

    /**
     * Delete a transaction by account number and transaction ID
     */
    public void deleteById(String accountNumber, String transactionId) {
        Key key = Key.builder()
                .partitionValue("ACCOUNT#" + accountNumber)
                .sortValue("TXN#" + transactionId)
                .build();

        log.info("Deleting transaction {} for account {}, user: {}",
                transactionId, accountNumber, defaultUserId);

        transactionTable.deleteItem(key);
    }

    /**
     * Delete all transactions for an account
     */
    public void deleteByAccountNumber(String accountNumber) {
        log.info("Deleting all transactions for account {}, user: {}",
                accountNumber, defaultUserId);

        List<Transaction> transactions = findByAccountNumber(accountNumber);
        for (Transaction txn : transactions) {
            deleteById(accountNumber, txn.getTxnId());
        }

        log.info("Deleted {} transactions for account {}",
                transactions.size(), accountNumber);
    }

    /**
     * Count all transactions in the table
     */
    public long count() {
        long count = transactionTable.scan().items().stream().count();
        log.info("Counted {} total transactions, user: {}", count, defaultUserId);
        return count;
    }
}