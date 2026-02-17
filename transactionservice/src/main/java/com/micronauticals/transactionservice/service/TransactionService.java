package com.micronauticals.transactionservice.service;

import com.micronauticals.transactionservice.dto.DataRefreshPull;
import com.micronauticals.transactionservice.dto.FIPResponseDTO;
import com.micronauticals.transactionservice.entity.financialdata.FiDataBundle;
import com.micronauticals.transactionservice.entity.financialdata.Transaction;
import com.micronauticals.transactionservice.exception.SetuLoginException;
import com.micronauticals.transactionservice.mapper.FIPResponseDtoToEntityMapper;
import com.micronauticals.transactionservice.repository.FIDataRepository;
import com.micronauticals.transactionservice.repository.TransactionRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class TransactionService implements com.micronauticals.transactionservice.service.TransactionServiceInterface.TransactionService {

    @Value("${setu.product.instance.id}")
    private String productInstanceID;
    private final FIDataRepository fiDataRepository;
    private final FIPResponseDtoToEntityMapper fipResponseDtoToEntityMapper;
    private final TransactionRepository transactionRepository;
    private final WebClient.Builder webClientBuilder;
    private static final DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final String RAG_SERVICE_URL = "http://ragservice:9000/ingest";

    @Override
    public Mono<FIPResponseDTO> getFiData(String sessionId, String authorization) {
        String timestamp = LocalDateTime.now().format(formatter);
        log.info("Fetching financial data for session ID: {}, user: {}, timestamp: {}",
                sessionId, timestamp);

        if (authorization == null) {
            return Mono.error(new SetuLoginException("Access token not available. Please login first."));
        }

        WebClient webClient = webClientBuilder.build();
        String url = String.format("https://fiu-sandbox.setu.co/v2/sessions/%s", sessionId);

        return webClient.get()
                .uri(url)
                .header(HttpHeaders.AUTHORIZATION, String.format("Bearer %s", authorization))
                .header("x-product-instance-id", productInstanceID)
                .retrieve()
                .onStatus(status -> !status.is2xxSuccessful(), response -> {
                    log.error("Failed to fetch consent status. HTTP Status: {}", response.statusCode());
                    return response.bodyToMono(String.class)
                            .flatMap(errorBody -> {
                                log.error("Error body: {}, user: {}", errorBody);
                                return Mono.error(new RuntimeException("Error fetching financial data: " + errorBody));
                            });
                })
                .bodyToMono(FIPResponseDTO.class)
                .flatMap(response -> Mono.fromCallable(() -> {
                    try {
                        log.info("Processing financial data for consent ID: {}, user: {}",
                                response.getConsentId());

                        // Step 1: Map DTO to entity and save to PostgreSQL
                        FiDataBundle fiDataBundle = fipResponseDtoToEntityMapper.mapToEntity(response);
                        FiDataBundle savedBundle = fiDataRepository.save(fiDataBundle);
                        log.info("Saved FiDataBundle with ID: {} to PostgreSQL, user: {}",
                                savedBundle.getId());

                        // Step 2: Extract transactions from the mapper
                        List<Transaction> transactions = fipResponseDtoToEntityMapper.extractAllTransactions(response.getConsentId());
                        log.info("Extracted {} transactions for DynamoDB storage, user: {}",
                                transactions.size());

                        // Step 3: Save all transactions to DynamoDB in batch
                        if (!transactions.isEmpty()) {
                            transactionRepository.saveAll(transactions);
                            log.info("Successfully saved all {} transactions to DynamoDB, user: {}",
                                    transactions.size());
                        } else {
                            log.info("No transactions to save to DynamoDB, user");
                        }

                        return response;
                    } catch (Exception e) {
                        log.error("Error processing financial data, user: {}, error: {}",
                                e.getMessage(), e);
                        throw e;
                    }
                }).subscribeOn(Schedulers.boundedElastic()))
                .doOnNext(response -> log.info("Financial data processing completed successfully for consent ID: {}, user: {}",
                        response.getConsentId()))
                .doOnError(error -> log.error("Failed to process financial data, user: {}, error: {}"
                        , error.getMessage(), error));
    }


    /**
     * Sends transactions to the RAG service ingest endpoint
     * @param transactions List of transactions to send
     * @return Mono<Void> indicating completion
     */
    public Mono<Void> sendTransactionsToRagService(List<Transaction> transactions) {
        log.info("⚡ sendTransactionsToRagService called with {} transactions", transactions.size());

        WebClient webClient = webClientBuilder.build();
        
        // Wrap transactions in the required format
        Map<String, List<Transaction>> requestBody = Map.of("context_data", transactions);

        log.info("📤 Sending {} transactions to RAG service at {}", transactions.size(), RAG_SERVICE_URL);
        log.debug("Request body contains context_data with {} items", requestBody.get("context_data").size());

        return webClient.post()
                .uri(RAG_SERVICE_URL)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(requestBody)
                .retrieve()
                .onStatus(status -> !status.is2xxSuccessful(), response -> {
                    log.error("❌ Failed to send transactions to RAG service. HTTP Status: {}", response.statusCode());
                    return response.bodyToMono(String.class)
                            .flatMap(errorBody -> {
                                log.error("RAG service error body: {}", errorBody);
                                return Mono.error(new RuntimeException("Error sending to RAG service: " + errorBody));
                            });
                })
                .bodyToMono(Void.class)
                .doOnSubscribe(subscription -> log.info("🔔 WebClient subscription activated"))
                .doOnSuccess(v -> log.info("✅ Successfully sent {} transactions to RAG service", transactions.size()))
                .doOnError(error -> log.error("❌ Error sending transactions to RAG service: {}", error.getMessage(), error))
                .doFinally(signalType -> log.info("🏁 RAG service call finished with signal: {}", signalType));
    }


    @Override
    public Mono<DataRefreshPull> refreshDataPull(String sessionID, boolean restart) {
        return null;
    }
}
