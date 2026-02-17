package com.micronauticals.accountservice.service.SetuServiceImpl;
import com.micronauticals.accountservice.Dto.request.ConsentRequestDTO;
import com.micronauticals.accountservice.Dto.request.SetuLoginRequest;
import com.micronauticals.accountservice.Dto.response.consent.ConsentDataSessionResponseDTO;
import com.micronauticals.accountservice.Dto.response.consent.ConsentResponse;
import com.micronauticals.accountservice.Dto.response.consent.ConsentStatusResponseDTO;
import com.micronauticals.accountservice.Dto.response.consent.RevokeConsentResponse;
import com.micronauticals.accountservice.Dto.response.financialdata.DataRefreshPull;
import com.micronauticals.accountservice.Dto.response.financialdata.FIPResponseDTO;
import com.micronauticals.accountservice.Dto.response.financialdata.SetuLoginResponse;
import com.micronauticals.accountservice.entity.consent.Consent;
import com.micronauticals.accountservice.entity.consent.ConsentDataSession;
import com.micronauticals.accountservice.entity.financialdata.FiDataBundle;
import com.micronauticals.accountservice.entity.financialdata.Transaction;
import com.micronauticals.accountservice.exception.SetuLoginException;
import com.micronauticals.accountservice.mapper.ConsentDataSessionToEntity;
import com.micronauticals.accountservice.mapper.ConsentDtoToEntity;
import com.micronauticals.accountservice.mapper.FIPResponseDtoToEntityMapper;
import com.micronauticals.accountservice.repository.ConsentDataSessionRepository;
import com.micronauticals.accountservice.repository.ConsentRepository;
import com.micronauticals.accountservice.repository.FIDataRepository;
import com.micronauticals.accountservice.repository.TransactionRepository;
import com.micronauticals.accountservice.service.SetuServiceInterface.SetuAuthService;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.time.Duration;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;


@Service
@RequiredArgsConstructor
public class SetuAuthServiceImpl implements SetuAuthService {

    private final WebClient.Builder webClientBuilder;
    private final ConsentRepository consentRepository;
    private final ConsentDtoToEntity consentDtoToEntity;
    private final FIDataRepository fiDataRepository;
    private final FIPResponseDtoToEntityMapper fipResponseDtoToEntityMapper;
    private final ConsentDataSessionToEntity consentDataSessionToEntity ;
    private final ConsentDataSessionRepository consentDataSessionRepository;
    private final TransactionRepository transactionRepository;

    @Value("${setu.product.instance.id}")
    private String productInstanceID;

    @Value("${setu.grantType}")
    private String grantType;

    @Value("${setu.clientID}")
    private String clientID;

    @Value("${setu.secret}")
    private String secret;

    private static final String SETU_LOGIN_URL = "https://orgservice-prod.setu.co/v1/users/login";
    private static final String SETU_CONSENT_URL = "https://fiu-sandbox.setu.co/v2/consents";
    private static final Logger log = LoggerFactory.getLogger(SetuAuthServiceImpl.class);
    private static final DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final String RAG_SERVICE_URL = "http://ragservice:9000/ingest";
    private static final String RAG_PROMPT_URL = "http://ragservice:9000/prompt";

    private String accessToken;
    private String refreshToken;

    @Override
    public SetuLoginResponse login() {
        try {
            WebClient webClient = webClientBuilder.build();

            Mono<Map> responseMono = webClient.post()
                    .uri(SETU_LOGIN_URL)
                    .header("client", "bridge")
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(Map.of(
                            "grant_type", grantType,
                            "clientID", clientID,
                            "secret", secret
                    ))
                    .retrieve()
                    .onStatus(HttpStatusCode::isError, clientResponse -> {
                        HttpStatusCode statusCode = clientResponse.statusCode();
                        return clientResponse.bodyToMono(String.class)
                                .onErrorReturn("Unable to read error response")
                                .timeout(Duration.ofSeconds(5))
                                .flatMap(errorBody -> {
                                    String sanitizedError = sanitizeErrorMessage(errorBody);
                                    log.error("Setu API error - Status: {}, Response: {}", statusCode, sanitizedError);
                                    return Mono.error(new SetuLoginException("Setu login failed with status " + statusCode.value()));
                                });
                    })
                    .bodyToMono(Map.class);

            Map<String, Object> result = responseMono.block();

            if (result == null || !result.containsKey("access_token")) {
                throw new SetuLoginException("Missing access token in Setu response");
            }

            this.accessToken = (String) result.get("access_token");
            this.refreshToken = (String) result.get("refresh_token");

            log.info("Received access token from Setu");

            return SetuLoginResponse.builder()
                    .accessToken(this.accessToken)
                    .refreshToken(this.refreshToken)
                    .build();

        } catch (Exception ex) {
            log.error("Error during Setu login", ex);
            throw new SetuLoginException("Error during Setu login: " + ex.getMessage(), ex);
        }
    }

    @Override
    public Mono<ConsentResponse> createConsent(ConsentRequestDTO requestDTO) {
        if (accessToken == null) {
            return Mono.error(new SetuLoginException("Access token not available. Please login first."));
        }
        WebClient webClient = webClientBuilder.build();
        return webClient.post()
                .uri(SETU_CONSENT_URL)
                .header(HttpHeaders.AUTHORIZATION, String.format("Bearer %s",accessToken))
                .header("x-product-instance-id", productInstanceID)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(requestDTO)
                .retrieve()
                .onStatus(status -> !status.is2xxSuccessful(), response -> {
                    log.error("Failed to create consent. HTTP Status: {}", response.statusCode());
                    return response.bodyToMono(String.class)
                            .flatMap(errorBody -> {
                                log.error("Error body: {}", errorBody);
                                return Mono.error(new RuntimeException("Error creating consent: " + errorBody));
                            });
                })
                .bodyToMono(ConsentResponse.class)
                .flatMap(response -> Mono.fromCallable(() -> {
                    Consent consent = consentDtoToEntity.mapToEntity(response);
                    consentRepository.save(consent);
                    log.info("Consent saved in DB with ID: {}", consent.getId());
                    return response;
                }).subscribeOn(Schedulers.boundedElastic()))
                .doOnNext(response -> log.info("Consent created successfully: {}", response))
                .doOnError(error -> log.error("Error occurred during consent creation", error));

    }

    @Override
    public Mono<ConsentStatusResponseDTO> getConsentStatus(String consentId, boolean expanded) {
        if (accessToken == null) {
            return Mono.error(new SetuLoginException("Access token not available. Please login first."));
        }

        WebClient webClient = webClientBuilder.build();

        String url = String.format("https://fiu-sandbox.setu.co/v2/consents/%s?expanded=%s", consentId, expanded);

        return webClient.get()
                .uri(url)
                .header(HttpHeaders.AUTHORIZATION, String.format("Bearer %s",accessToken))
                .header("x-product-instance-id", productInstanceID)
                .retrieve()
                .onStatus(status -> !status.is2xxSuccessful(), response -> {
                    log.error("Failed to fetch consent status. HTTP Status: {}", response.statusCode());
                    return response.bodyToMono(String.class)
                            .flatMap(errorBody -> {
                                log.error("Error body: {}", errorBody);
                                return Mono.error(new RuntimeException("Error fetching consent status: " + errorBody));
                            });
                })
                .bodyToMono(ConsentStatusResponseDTO.class)
                .doOnNext(response -> log.info("Consent status fetched successfully: {}", response))
                .doOnError(error -> log.error("Error occurred while fetching consent status", error));
    }

    @Override
    public Mono<ConsentDataSessionResponseDTO> getDataSessionByConsentId(String consentId){

        if (accessToken == null) {
            return Mono.error(new SetuLoginException("Access token not available. Please login first."));
        }

        WebClient webClient = webClientBuilder.build();

        String url = String.format("https://fiu-sandbox.setu.co/v2/consents/%s/data-sessions",consentId);

        return webClient.get()
                .uri(url)
                .header(HttpHeaders.AUTHORIZATION, String.format("Bearer %s",accessToken))
                .header("x-product-instance-id", productInstanceID)
                .retrieve()
                .onStatus(status -> !status.is2xxSuccessful(), response -> {
                    log.error("Failed to fetch consent status. HTTP Status: {}", response.statusCode());
                    return response.bodyToMono(String.class)
                            .flatMap(errorBody -> {
                                log.error("Error body: {}", errorBody);
                                return Mono.error(new RuntimeException("Error fetching consent status: " + errorBody));
                            });
                })
                .bodyToMono(ConsentDataSessionResponseDTO.class)
                .flatMap(response -> Mono.fromCallable(() -> {
                    ConsentDataSession consentDataSession = consentDataSessionToEntity.mapToEntity(response);
                    consentDataSessionRepository.save(consentDataSession);
                    log.info("Data saved in DB with ID: {}", consentDataSession.getConsentId());
                    return response;
                }).subscribeOn(Schedulers.boundedElastic()))
                .doOnNext(response -> log.info("Consent status fetched successfully: {}", response))
                .doOnError(error -> log.error("Error occurred while fetching consent status", error));

    }

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
                        log.info(String.valueOf(fiDataBundle));
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
                            log.info("Successfully saved all {} transactions to DynamoDB", transactions.size());

                            // Step 4: Send to RAG service asynchronously (fire and forget)
                            sendTransactionsToRagService(transactions)
                                .doOnSuccess(result -> log.info("Successfully sent {} transactions to RAG service endpoint",
                                        transactions.size()))
                                .doOnError(e -> log.error("Failed to send transactions to RAG service: {}", e.getMessage(), e))
                                .subscribeOn(Schedulers.boundedElastic())
                                .subscribe(); // Non-blocking subscribe
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

    public Mono<RevokeConsentResponse> revokeConsent(String consentID){
        WebClient webClient = webClientBuilder.build();
        String url = String.format("https://fiu-sandbox.setu.co/v2/consents/%s/revoke",consentID);
        return webClient.post()
                .uri(url)
                .header(HttpHeaders.AUTHORIZATION, String.format("Bearer %s",accessToken))
                .header("x-product-instance-id", productInstanceID)
                .retrieve()
                .onStatus(status -> !status.is2xxSuccessful(), response -> {
                    log.error("Failed to revoke consent. HTTP Status: {}", response.statusCode());
                    return response.bodyToMono(String.class)
                            .flatMap(errorBody -> {
                                log.error("Error body: {}", errorBody);
                                return Mono.error(new RuntimeException("Error fetching consent status: " + errorBody));
                            });
                })
                .bodyToMono(RevokeConsentResponse.class)
                .doOnNext(response -> log.info("Consent revoked successfully: {}", response))
                .doOnError(error -> log.error("Error occurred while fetching consent status", error));
    }

    @Override
    public Mono<DataRefreshPull> refreshDataPull(String sessionID, boolean restart){
        String url = restart
                ? String.format("https://fiu-sandbox.setu.co/v2/sessions/refresh/%s?restart=true",sessionID)
                : String.format("https://fiu-sandbox.setu.co/v2/sessions/refresh/%s",sessionID);

        WebClient webClient = webClientBuilder.build();
        return webClient.post()
                .uri(url)
                .header(HttpHeaders.AUTHORIZATION, String.format("Bearer %s",accessToken))
                .header("x-product-instance-id", productInstanceID)
                .retrieve()
                .onStatus(status -> !status.is2xxSuccessful(),response -> {
                    log.error("Error occured while refreshing data. HTTP Status: {}",response.statusCode());
                    return response.bodyToMono(String.class)
                            .flatMap(errorBody ->{
                                return Mono.error(new RuntimeException("Error refreshing data: " + errorBody));
                            });
                })
                .bodyToMono(DataRefreshPull.class)
                .doOnNext(response -> log.info("Data refreshed successfully: {}", response))
                .doOnError(error -> log.error("Error occurred while refreshing data", error));
    }


    /**
     * Sends transactions to the RAG service ingest endpoint
     * @param transactions List of transactions to send
     * @return Mono<Void> indicating completion
     */
    private Mono<Void> sendTransactionsToRagService(List<Transaction> transactions) {
        WebClient webClient = webClientBuilder.build();

        return webClient.post()
                .uri(RAG_SERVICE_URL)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(transactions)
                .retrieve()
                .onStatus(status -> !status.is2xxSuccessful(), response -> {
                    log.error("Failed to send transactions to RAG service. HTTP Status: {}", response.statusCode());
                    return response.bodyToMono(String.class)
                            .flatMap(errorBody -> {
                                log.error("RAG service error body: {}", errorBody);
                                return Mono.error(new RuntimeException("Error sending to RAG service: " + errorBody));
                            });
                })
                .bodyToMono(Void.class)
                .doOnSuccess(v -> log.info("Successfully sent transactions to RAG service"))
                .doOnError(error -> log.error("Error sending transactions to RAG service", error));
    }

    /**
     * Bypass method to send prompt to RAG service and get AI response
     * @param prompt The prompt/question from frontend
     * @return Mono<Map> containing the AI response
     */
    public Mono<Map<String, Object>> sendPromptToRagService(String prompt) {
        log.info("Sending prompt to RAG service: {}", prompt);

        WebClient webClient = webClientBuilder.build();

        Map<String, String> requestBody = Map.of("prompt", prompt);

        return webClient.post()
                .uri(RAG_PROMPT_URL)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(requestBody)
                .retrieve()
                .onStatus(status -> !status.is2xxSuccessful(), response -> {
                    log.error("Failed to get response from RAG service. HTTP Status: {}", response.statusCode());
                    return response.bodyToMono(String.class)
                            .flatMap(errorBody -> {
                                log.error("RAG service error: {}", errorBody);
                                return Mono.error(new RuntimeException("Error from RAG service: " + errorBody));
                            });
                })
                .bodyToMono(new org.springframework.core.ParameterizedTypeReference<Map<String, Object>>() {})
                .doOnSuccess(response -> log.info("Successfully received response from RAG service"))
                .doOnError(error -> log.error("Error getting response from RAG service: {}", error.getMessage()))
                .onErrorResume(error -> {
                    log.error("RAG service call failed, returning error response", error);
                    return Mono.just(Map.of(
                            "response", "Failed to get AI response: " + error.getMessage(),
                            "status", "error"
                    ));
                });
    }

    private String sanitizeErrorMessage(String errorBody) {
        if (errorBody == null || errorBody.trim().isEmpty()) {
            return "Empty error response";
        }
        return errorBody.length() > 200 ? errorBody.substring(0, 200) + "..." : errorBody;
    }
}
