package com.micronauticals.accountservice.service.SetuServiceInterface;

import com.micronauticals.accountservice.Dto.request.ConsentRequestDTO;
import com.micronauticals.accountservice.Dto.request.SetuLoginRequest;
import com.micronauticals.accountservice.Dto.response.consent.ConsentDataSessionResponseDTO;
import com.micronauticals.accountservice.Dto.response.consent.ConsentResponse;
import com.micronauticals.accountservice.Dto.response.consent.ConsentStatusResponseDTO;
import com.micronauticals.accountservice.Dto.response.consent.RevokeConsentResponse;
import com.micronauticals.accountservice.Dto.response.financialdata.DataRefreshPull;
import com.micronauticals.accountservice.Dto.response.financialdata.FIPResponseDTO;
import com.micronauticals.accountservice.Dto.response.financialdata.SetuLoginResponse;
import reactor.core.publisher.Mono;

import java.util.Map;

public interface SetuAuthService {
    SetuLoginResponse login();
    Mono<ConsentResponse> createConsent(ConsentRequestDTO request);
    Mono<ConsentStatusResponseDTO> getConsentStatus(String consentId, boolean expanded);
    Mono<ConsentDataSessionResponseDTO> getDataSessionByConsentId(String consentId);
    Mono<FIPResponseDTO> getFiData(String sessionId,String authorization);
    Mono<RevokeConsentResponse> revokeConsent(String consentID);
    Mono<DataRefreshPull> refreshDataPull(String sessionID, boolean restart);

    /**
     * Bypass method to forward prompt to RAG service and return AI response
     * @param prompt The prompt/question from frontend
     * @return Mono<Map> containing the AI response with "response" and "status" fields
     */
    Mono<Map<String, Object>> sendPromptToRagService(String prompt);
}
