package com.micronauticals.gatewayserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.cloud.gateway.filter.ratelimit.RedisRateLimiter;
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.time.LocalDateTime;

@SpringBootApplication
public class GatewayserverApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayserverApplication.class, args);
    }

    @Bean
    public RouteLocator liveReconAIConfig(RouteLocatorBuilder routeLocatorBuilder){
        return routeLocatorBuilder.routes()
                .route(p -> p.path("/livereconai/prod/v1/account/**")
                        .filters(f->f.rewritePath(
                                "/livereconai/prod/v1/account/(?<segment>.*)",
                                "/${segment}")
                        .addResponseHeader("X-Response-Time", LocalDateTime.now().toString())
                        .retry(retryConfig -> retryConfig.setRetries(5)
                                .setMethods(HttpMethod.GET)
                                .setBackoff(Duration.ofMillis(100),Duration.ofMillis(1000),2,true)
                        )
                        .circuitBreaker(config -> config.setName("AccountCircuitBreaker"))
                        .requestRateLimiter(config -> config.setRateLimiter(redisRateLimiter()).setKeyResolver(keyResolver())))
                        .uri("http://accounts:8072")
                )
                .route(p -> p.path("/livereconai/prod/v1/auth/**")
                        .filters(f->f.rewritePath(
                                "/livereconai/prod/v1/auth/(?<segment>.*)",
                                "/${segment}")
                        .addResponseHeader("X-Response-Time", LocalDateTime.now().toString())
                        .retry(retryConfig -> retryConfig.setRetries(5)
                                .setMethods(HttpMethod.GET)
                                .setBackoff(Duration.ofMillis(100),Duration.ofMillis(1000),2,true)
                        )
                        .circuitBreaker(config -> config.setName("AuthCircuitBreaker"))
                        .requestRateLimiter(config -> config.setRateLimiter(redisRateLimiter()).setKeyResolver(keyResolver())))
                        .uri("http://authservice:8086")
                )
                .route(p -> p.path("/livereconai/prod/v1/transaction/**")
                        .filters(f->f.rewritePath(
                                        "/livereconai/prod/v1/transaction/(?<segment>.*)",
                                        "/${segment}")
                                .addResponseHeader("X-Response-Time", LocalDateTime.now().toString())
                                .retry(retryConfig -> retryConfig.setRetries(5)
                                        .setMethods(HttpMethod.GET)
                                        .setBackoff(Duration.ofMillis(100),Duration.ofMillis(1000),2,true)
                                )
                                .circuitBreaker(config -> config.setName("TransactionCircuitBreaker"))
                                .requestRateLimiter(config -> config.setRateLimiter(redisRateLimiter()).setKeyResolver(keyResolver())))
                        .uri("http://transaction:8085")
                )
                .build();
    }

    @Bean
    public RedisRateLimiter redisRateLimiter(){
        return new RedisRateLimiter(1,1,1);
    }

    @Bean
    KeyResolver keyResolver(){
        return exchange -> Mono.justOrEmpty(exchange.getRequest().getHeaders().getFirst("user"));
    }

}
