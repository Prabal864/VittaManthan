package com.micronauticals.authservices.service.impl;

import com.micronauticals.authservices.dto.*;
import com.micronauticals.authservices.entity.User;
import com.micronauticals.authservices.enums.UserRole;
import com.micronauticals.authservices.exception.ResourceNotFoundException;
import com.micronauticals.authservices.exception.UserAlreadyExistsException;
import com.micronauticals.authservices.repository.UserRepository;
import com.micronauticals.authservices.service.UserService;
import com.micronauticals.authservices.utils.JwtUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class UserServiceImpl implements UserService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtil jwtUtil;
    private final AuthenticationManager authenticationManager;

    @Override
    public AuthResponse registerUser(RegisterRequest registerRequest) {
        // Check if username or email already exists
        if (userRepository.existsByUsername(registerRequest.getUsername())) {
            throw new UserAlreadyExistsException("Username is already taken");
        }

        if (userRepository.existsByEmail(registerRequest.getEmail())) {
            throw new UserAlreadyExistsException("Email is already in use");
        }

        if (registerRequest.getPhoneNumber() != null &&
                userRepository.existsByPhoneNumber(registerRequest.getPhoneNumber())) {
            throw new UserAlreadyExistsException("Phone number is already in use");
        }

        // Create new user
        User user = User.builder()
                .username(registerRequest.getUsername())
                .email(registerRequest.getEmail())
                .password(passwordEncoder.encode(registerRequest.getPassword()))
                .firstName(registerRequest.getFirstName())
                .lastName(registerRequest.getLastName())
                .phoneNumber(registerRequest.getPhoneNumber())
                .role(UserRole.USER)
                .build();

        User savedUser = userRepository.save(user);

        // Generate JWT tokens

        return AuthResponse.builder()
                .userId(savedUser.getId())
                .username(savedUser.getUsername())
                .build();
    }

    @Override
    public AuthResponse authenticateUser(LoginRequest loginRequest) {
        log.info("Login attempt for username: {}", loginRequest.getUsername());
        Authentication authentication = null;
        try {
            authentication = authenticationManager.authenticate(
                    new UsernamePasswordAuthenticationToken(
                            loginRequest.getUsername(),
                            loginRequest.getPassword()
                    )
            );
        } catch(org.springframework.security.core.AuthenticationException e){
            log.error("Authentication failed for username: {} - Reason: {}", loginRequest.getUsername(), e.getMessage());
            throw new com.micronauticals.authservices.exception.AuthenticationException("Invalid username or password");
        }

        User user = userRepository.findByUsername(loginRequest.getUsername())
                .orElseThrow(() -> new ResourceNotFoundException("User not found"));

        String role = user.getRole().name();

        String accessToken = jwtUtil.generateToken(authentication.getName(), role);
        String refreshToken = jwtUtil.generateRefreshToken(authentication.getName(), role);

        return AuthResponse.builder()
                .userId(user.getId())
                .username(user.getUsername())
                .accessToken(accessToken)
                .refreshToken(refreshToken)
                .build();
    }

    @Override
    public AuthResponse refreshToken(String refreshToken) {
        try {
            // First validate the token structure and signature
            if (!jwtUtil.validateToken(refreshToken)) {
                log.error("Invalid refresh token provided");
                throw new com.micronauticals.authservices.exception.AuthenticationException("Invalid refresh token");
            }

            // Extract username from the token
            String username = jwtUtil.getUsernameFromToken(refreshToken);

            if (username == null || username.trim().isEmpty()) {
                log.error("Refresh token contains empty or null username");
                throw new com.micronauticals.authservices.exception.AuthenticationException("Invalid refresh token: missing username");
            }

            log.debug("Attempting to refresh token for username: {}", username);

            // Find user in database with detailed logging
            Optional<User> userOptional = userRepository.findByUsername(username);

            if (userOptional.isEmpty()) {
                log.error("User not found in database for username: {} from refresh token", username);
                // Clear any existing authentication context
                SecurityContextHolder.clearContext();
                throw new com.micronauticals.authservices.exception.AuthenticationException("User account no longer exists. Please login again.");
            }

            User user = userOptional.get();
            log.debug("Successfully found user: {} with ID: {}", user.getUsername(), user.getId());

            // Generate new tokens
            String newAccessToken = jwtUtil.generateToken(username, user.getRole().name());
            String newRefreshToken = jwtUtil.generateRefreshToken(username, user.getRole().name());

            log.info("Successfully refreshed tokens for user: {}", username);

            return AuthResponse.builder()
                    .userId(user.getId())
                    .username(user.getUsername())
                    .accessToken(newAccessToken)
                    .refreshToken(newRefreshToken)
                    .build();

        } catch (Exception e) {
            log.error("Error during token refresh: {}", e.getMessage(), e);
            // Clear authentication context on any error
            SecurityContextHolder.clearContext();

            // Rethrow with more specific error messages
            if (e instanceof RuntimeException) {
                throw e;
            } else {
                throw new com.micronauticals.authservices.exception.AuthenticationException("Token refresh failed: " + e.getMessage());
            }
        }
    }


    @Override
    public boolean verifyToken(String token) {
        return jwtUtil.validateToken(token);
    }

    @Override
    public UserProfileResponse getUserProfile(String username) {
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new ResourceNotFoundException("User not found"));

        return UserProfileResponse.builder()
                .id(user.getId())
                .username(user.getUsername())
                .email(user.getEmail())
                .firstName(user.getFirstName())
                .lastName(user.getLastName())
                .phoneNumber(user.getPhoneNumber())
                .role(user.getRole())
                .createdAt(user.getCreatedAt())
                .build();
    }

    @Override
    public UserProfileResponse updateUserProfile(String username, ProfileUpdateRequest updateRequest) {
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new ResourceNotFoundException("User not found"));

        if (updateRequest.getFirstName() != null) {
            user.setFirstName(updateRequest.getFirstName());
        }

        if (updateRequest.getLastName() != null) {
            user.setLastName(updateRequest.getLastName());
        }

        if (updateRequest.getPhoneNumber() != null &&
                !updateRequest.getPhoneNumber().equals(user.getPhoneNumber())) {
            if (userRepository.existsByPhoneNumber(updateRequest.getPhoneNumber())) {
                throw new UserAlreadyExistsException("Phone number is already in use");
            }
            user.setPhoneNumber(updateRequest.getPhoneNumber());
        }

        User updatedUser = userRepository.save(user);

        return UserProfileResponse.builder()
                .id(updatedUser.getId())
                .username(updatedUser.getUsername())
                .email(updatedUser.getEmail())
                .firstName(updatedUser.getFirstName())
                .lastName(updatedUser.getLastName())
                .phoneNumber(updatedUser.getPhoneNumber())
                .role(updatedUser.getRole())
                .createdAt(updatedUser.getCreatedAt())
                .build();
    }

    @Override
    public Optional<User> findByUsername(String username) {
        return userRepository.findByUsername(username);
    }

    @Override
    public Optional<UserDto> findUserByPhoneNumber(String phoneNumber) {
        return userRepository.findByPhoneNumber(phoneNumber)
                .map(user -> UserDto.builder()
                        .id(user.getId())
                        .username(user.getUsername())
                        .email(user.getEmail())
                        .firstName(user.getFirstName())
                        .lastName(user.getLastName())
                        .phoneNumber(user.getPhoneNumber())
                        .role(user.getRole())
                        .build());
    }

    @Override
    public Map<String, Object> verifyTokenForInternalService(String token) {
        if (!jwtUtil.validateToken(token)) {
            throw new com.micronauticals.authservices.exception.AuthenticationException("Invalid token");
        }

        String username = jwtUtil.getUsernameFromToken(token);
        String role = jwtUtil.getRoleFromToken(token);

        Map<String, Object> result = new HashMap<>();
        result.put("valid", true);
        result.put("username", username);
        result.put("role", role);

        return result;
    }

    @Override
    public ApiResponse addConsentToUser(String username, String consentId) {
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new ResourceNotFoundException("User not found"));

        if (user.getConsentIds() == null) {
            user.setConsentIds(new java.util.ArrayList<>());
        }

        if (!user.getConsentIds().contains(consentId)) {
            user.getConsentIds().add(consentId);
            userRepository.save(user);
        }

        return new ApiResponse(true, "ConsentId saved for user");
    }

    @Override
    public UserConsentsResponse getUserConsents(String username) {
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new ResourceNotFoundException("User not found"));

        return UserConsentsResponse.builder()
                .username(user.getUsername())
                .consentIds(user.getConsentIds())
                .build();
    }

    @Override
    public UserConsentsResponse getUserConsentsByUserId(UUID userId) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User not found"));

        return UserConsentsResponse.builder()
                .username(user.getUsername())
                .consentIds(user.getConsentIds())
                .build();
    }
}
