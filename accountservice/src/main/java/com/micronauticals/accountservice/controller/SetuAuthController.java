package com.micronauticals.accountservice.controller;


import com.micronauticals.accountservice.Dto.request.ConsentIdsRequest;
import com.micronauticals.accountservice.Dto.request.ConsentRequestDTO;
import com.micronauticals.accountservice.Dto.request.SetuLoginRequest;
import com.micronauticals.accountservice.Dto.response.consent.ConsentDataSessionResponseDTO;
import com.micronauticals.accountservice.Dto.response.consent.ConsentDetailsResponse;
import com.micronauticals.accountservice.Dto.response.consent.ConsentResponse;
import com.micronauticals.accountservice.Dto.response.consent.ConsentStatusResponseDTO;
import com.micronauticals.accountservice.Dto.response.consent.ConsentsDetailsResponse;
import com.micronauticals.accountservice.Dto.response.consent.RevokeConsentResponse;
import com.micronauticals.accountservice.Dto.response.financialdata.DataRefreshPull;
import com.micronauticals.accountservice.Dto.response.financialdata.FIPResponseDTO;
import com.micronauticals.accountservice.Dto.response.financialdata.SetuLoginResponse;
import com.micronauticals.accountservice.entity.consent.Consent;
import com.micronauticals.accountservice.repository.ConsentRepository;
import com.micronauticals.accountservice.service.SetuServiceInterface.SetuAuthService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.*;
import java.util.function.Function;
import java.util.stream.Collectors;

@Slf4j
@RestController
@RequestMapping("/api/setu/auth")
@RequiredArgsConstructor
public class SetuAuthController {

    private final SetuAuthService setuAuthService;
    private final ConsentRepository consentRepository;

    @PostMapping("/login")
    public ResponseEntity<SetuLoginResponse> login() {
        SetuLoginResponse response = setuAuthService.login();
        return ResponseEntity.ok(response);
    }

    @PostMapping("/consent")
    public Mono<ResponseEntity<ConsentResponse>> createConsent(@RequestBody ConsentRequestDTO consentRequestDTO) {
        return setuAuthService.createConsent(consentRequestDTO)
                .map(ResponseEntity::ok)
                .onErrorResume(e -> Mono.just(ResponseEntity.status(500).build()));
    }

    @GetMapping("/{consentId}/status")
    public Mono<ResponseEntity<ConsentStatusResponseDTO>> getConsentStatus(
            @PathVariable String consentId,
            @RequestParam(defaultValue = "false") boolean expanded) {

        return setuAuthService.getConsentStatus(consentId, expanded)
                .map(ResponseEntity::ok)
                .onErrorResume(error -> {
                    // Optionally log the error here
                    return Mono.just(ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(null));
                });
    }

    @GetMapping("/{consentId}/consentDataSession")
    public Mono<ResponseEntity<ConsentDataSessionResponseDTO>> getConsentDataSessions(
            @PathVariable String consentId) {

        return setuAuthService.getDataSessionByConsentId(consentId)
                .map(ResponseEntity::ok)
                .onErrorResume(error -> {
                    // Optionally log the error here
                    return Mono.just(ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(null));
                });
    }


    @GetMapping("/{sessionId}/getFiData")
    public Mono<ResponseEntity<FIPResponseDTO>> getFiDataBySessionId(
            @PathVariable String sessionId, @RequestHeader("Authorization") String authorization ) {

        return setuAuthService.getFiData(sessionId, authorization.substring(7))
                .map(ResponseEntity::ok)
                .onErrorResume(error -> {
                    // Optionally log the error here
                    return Mono.just(ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(null));
                });
    }

    @PostMapping("/{consentID}/revokeConsent")
    public Mono<ResponseEntity<RevokeConsentResponse>> revokeConsentByConsentID(
            @PathVariable String consentID) {
        return setuAuthService.revokeConsent(consentID)
                .map(ResponseEntity::ok)
                .onErrorResume(error -> Mono.just(ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(null)));
    }

    @PostMapping("/{sessionID}/refreshDataPull")
    public Mono<ResponseEntity<DataRefreshPull>> getRefreshDataBySessionID(@PathVariable String sessionID, @RequestParam(required = false,name = "restart",defaultValue = "false") boolean restart){
        return setuAuthService.refreshDataPull(sessionID, restart)
                .map(ResponseEntity::ok)
                .onErrorResume(error -> Mono.just(ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(null)));
    }

    /** Fetch full details for a single consentId. */
    @GetMapping("/consents/{consentId}/details")
    public Mono<ResponseEntity<ConsentDetailsResponse>> getConsentDetails(
            @PathVariable String consentId,
            @RequestParam(defaultValue = "true") boolean expanded) {

        Consent persisted = consentRepository.findById(consentId).orElse(null);

        return Mono.zip(
                        setuAuthService.getConsentStatus(consentId, expanded),
                        setuAuthService.getDataSessionByConsentId(consentId)
                )
                .map(tuple -> ResponseEntity.ok(ConsentDetailsResponse.builder()
                        .consentId(consentId)
                        .persisted(persisted)
                        .status(tuple.getT1())
                        .dataSessions(tuple.getT2())
                        .build()))
                .onErrorResume(error -> {
                    log.error("Failed to fetch consent details for consentId={}", consentId, error);
                    return Mono.just(ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build());
                });
    }

    /**
     * Fetch full consent details for an array of consentIds.
     * Request body: { "consentIds": ["id1", "id2"] }
     */
    @PostMapping("/consents/details")
    public Mono<ResponseEntity<ConsentsDetailsResponse>> getConsentsDetails(
            @RequestBody ConsentIdsRequest request,
            @RequestParam(defaultValue = "true") boolean expanded) {

        if (request == null || request.getConsentIds() == null || request.getConsentIds().isEmpty()) {
            return Mono.just(ResponseEntity.badRequest().build());
        }

        // de-dup but keep order
        List<String> consentIds = request.getConsentIds().stream()
                .filter(Objects::nonNull)
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .distinct()
                .toList();

        if (consentIds.isEmpty()) {
            return Mono.just(ResponseEntity.badRequest().build());
        }

        // preload persisted consents in one DB call (optional)
        Map<String, Consent> persistedById = consentRepository.findAllByIdIn(consentIds).stream()
                .collect(Collectors.toMap(Consent::getId, Function.identity(), (a, b) -> a));

        return Flux.fromIterable(consentIds)
                .flatMap(consentId -> Mono.zip(
                                setuAuthService.getConsentStatus(consentId, expanded),
                                setuAuthService.getDataSessionByConsentId(consentId)
                        )
                        .map(tuple -> ConsentDetailsResponse.builder()
                                .consentId(consentId)
                                .persisted(persistedById.get(consentId))
                                .status(tuple.getT1())
                                .dataSessions(tuple.getT2())
                                .build())
                        .onErrorResume(error -> {
                            // partial failure: return consentId with DB snapshot, but null setu data
                            log.error("Failed to fetch Setu details for consentId={}", consentId, error);
                            return Mono.just(ConsentDetailsResponse.builder()
                                    .consentId(consentId)
                                    .persisted(persistedById.get(consentId))
                                    .status(null)
                                    .dataSessions(null)
                                    .build());
                        }))
                .collectList()
                .map(list -> ResponseEntity.ok(ConsentsDetailsResponse.builder().consents(list).build()));
    }

    /**
     * Bypass endpoint to forward prompt to RAG service and return AI response
     * Request body: { "prompt": "Your question or prompt text here" }
     * Response: { "response": "AI generated response", "status": "success" }
     */
    @PostMapping("/prompt")
    public Mono<ResponseEntity<Map<String, Object>>> sendPromptToAI(@RequestBody Map<String, String> request) {
        String prompt = request.get("prompt");

        if (prompt == null || prompt.trim().isEmpty()) {
            return Mono.just(ResponseEntity.badRequest().body(Map.of(
                    "response", "Prompt cannot be empty",
                    "status", "error"
            )));
        }

        return setuAuthService.sendPromptToRagService(prompt)
                .map(ResponseEntity::ok)
                .onErrorResume(error -> {
                    log.error("Error processing prompt request", error);
                    return Mono.just(ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(Map.of(
                            "response", "Failed to process prompt: " + error.getMessage(),
                            "status", "error"
                    )));
                });
    }

}