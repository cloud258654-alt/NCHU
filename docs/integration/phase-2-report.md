# Phase 2 Report: 匯入 BI-RMP 核心系統

## 執行日期

2026-07-17 15:36:12 +08:00

## 路徑

- 來源專案 B：D:\BI-RMP-main
- 目標工作區：D:\BI-RMP-V2

## 複製摘要

- Source included file count: 182
- Copied / merged file count: 182
- Excluded file count: 0
- `.gitignore` merged: True
- Source BI-RMP modified: False

## 排除檔案

- None

## 遺漏與原因

- None

## 靜態檢查

| Check | Status | ExitCode |
|---|---|---:|
| compileall | PASS | 0 |
| JSON validation | PASS | 0 |
| YAML validation | SKIPPED |  |
| Docker Compose config | PASS | 0 |
| pytest | SKIPPED |  |

### compileall output

    Listing 'Backend'...
    Listing 'Backend\\adapters'...
    Listing 'Backend\\adapters\\google_maps'...
    Listing 'Backend\\adapters\\ptt'...
    Listing 'Backend\\adapters\\threads'...
    Listing 'Backend\\adapters\\web'...
    Listing 'Backend\\api'...
    Listing 'Backend\\config'...
    Listing 'Backend\\core'...
    Listing 'Backend\\core\\anti_block'...
    Listing 'Backend\\scripts'...
    Listing 'Backend\\services'...
    Listing 'Backend\\services\\nlp_analysis'...
    Listing 'Backend\\services\\reputation_scoring'...
    Listing 'Backend\\tests'...
    Listing 'Backend\\tests\\adapters'...
    Listing 'Backend\\tests\\api'...
    Listing 'Backend\\tests\\core'...
    Listing 'Backend\\tests\\database'...
    Listing 'Backend\\tests\\scripts'...
    Listing 'Backend\\tests\\services'...

### JSON output

    validated 2 json files

### YAML output

    PyYAML is not installed in the current environment; YAML format check skipped without installing packages.

### Docker Compose output

    name: bi-rmp-n8n
    services:
      n8n:
        container_name: bi-rmp-n8n
        depends_on:
          postgres:
            condition: service_healthy
            required: true
        environment:
          BI_RMP_BACKEND_BASE_URL: http://host.docker.internal:8000
          BI_RMP_INTERNAL_API_KEY: change-this-internal-api-key
          DB_POSTGRESDB_DATABASE: n8n
          DB_POSTGRESDB_HOST: postgres
          DB_POSTGRESDB_PASSWORD: change-this-local-password
          DB_POSTGRESDB_PORT: "5432"
          DB_POSTGRESDB_SCHEMA: public
          DB_POSTGRESDB_USER: n8n
          DB_TYPE: postgresdb
          GENERIC_TIMEZONE: Asia/Taipei
          LINE_CHANNEL_ACCESS_TOKEN: ""
          LINE_CHANNEL_SECRET: ""
          N8N_BLOCK_ENV_ACCESS_IN_NODE: "false"
          N8N_DIAGNOSTICS_ENABLED: "false"
          N8N_ENCRYPTION_KEY: change-this-to-a-fixed-local-dev-encryption-key
          N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS: "true"
          N8N_HOST: localhost
          N8N_PERSONALIZATION_ENABLED: "false"
          N8N_PORT: "5678"
          N8N_PROTOCOL: http
          N8N_PROXY_HOPS: "0"
          N8N_SECURE_COOKIE: "false"
          NODE_FUNCTION_ALLOW_BUILTIN: crypto
          TZ: Asia/Taipei
          WEBHOOK_URL: http://localhost:5678/
        extra_hosts:
          - host.docker.internal=host-gateway
        image: docker.n8n.io/n8nio/n8n
        networks:
          bi-rmp-n8n: null
        ports:
          - mode: ingress
            host_ip: 127.0.0.1
            target: 5678
            published: "5678"
            protocol: tcp
        restart: unless-stopped
        volumes:
          - type: volume
            source: n8n_data
            target: /home/node/.n8n
            volume: {}
          - type: bind
            source: D:\BI-RMP-V2\infra\n8n\workflows
            target: /opt/bi-rmp/n8n-workflows
            bind: {}
      postgres:
        container_name: bi-rmp-n8n-postgres
        environment:
          POSTGRES_DB: n8n
          POSTGRES_PASSWORD: change-this-local-password
          POSTGRES_USER: n8n
        healthcheck:
          test:
            - CMD-SHELL
            - pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}
          timeout: 5s
          interval: 10s
          retries: 5
        image: postgres:16-alpine
        networks:
          bi-rmp-n8n: null
        restart: unless-stopped
        volumes:
          - type: volume
            source: n8n_postgres_data
            target: /var/lib/postgresql/data
            volume: {}
    networks:
      bi-rmp-n8n:
        name: bi-rmp-n8n_bi-rmp-n8n
        driver: bridge
    volumes:
      n8n_data:
        name: bi-rmp-n8n_n8n_data
      n8n_postgres_data:
        name: bi-rmp-n8n_n8n_postgres_data

### pytest output / reason

    未執行。安全審查要求避免在未知專案中執行 pytest 或 runtime dependency imports，因測試可能觸發外部連線或副作用；本階段僅完成靜態檢查。

## 秘密掃描摘要

只列出檔案路徑與疑似變數名稱，未輸出任何值。

- .env.example: BI_RMP_INTERNAL_API_KEY, DATABASE_URL, LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, N8N_DB_PASSWORD, password, secret, secrets, SUPABASE_SERVICE_ROLE_KEY, tokens
- .gitignore: secrets
- AGENTS.md: secrets
- README.md: DATABASE_URL
- .github\workflows\ci.yml: DATABASE_URL
- Backend\adapters\google_maps\config.py: GOOGLE_MAPS_MORE_TOKENS, GOOGLE_MAPS_RESTRICTED_TEXT_TOKENS, GOOGLE_MAPS_REVIEWS_TOKENS
- Backend\adapters\google_maps\crawler.py: MORE_TOKENS, RESTRICTED_TEXT_TOKENS, REVIEWS_TOKENS, token, tokens
- Backend\adapters\ptt\crawler.py: token, token_match_ratio
- Backend\adapters\threads\crawler.py: secrets, THREADS_CAPTCHA_TOKENS, THREADS_LOGIN_TOKENS, THREADS_RESTRICTED_TOKENS, token
- Backend\api\business.py: database_url, DATABASE_URL
- Backend\api\client_messages_log.py: database_url, DATABASE_URL
- Backend\api\client_recognition.py: database_url, DATABASE_URL
- Backend\api\enriched_reputation.py: database_url, DATABASE_URL
- Backend\api\liff_registration.py: id_token, LiffTokenVerifier, LINE_ID_TOKEN_VERIFY_URL
- Backend\api\line_registration_notification.py: channel_access_token, LINE_CHANNEL_ACCESS_TOKEN
- Backend\api\main.py: BI_RMP_INTERNAL_API_KEY, get_liff_token_verifier, id_token, LiffTokenVerifier, verify_internal_api_key, x_bi_rmp_api_key
- Backend\api\reputation.py: database_url, DATABASE_URL
- Backend\core\runtime_settings.py: DATABASE_URL
- Backend\core\supabase.py: database_url, DATABASE_URL
- Backend\scripts\inspect_reviews_enriched.py: DATABASE_URL, secrets
- Backend\scripts\manage_rich_menu.py: get_token, LINE_CHANNEL_ACCESS_TOKEN, token
- Backend\scripts\verify_supabase_ingestion.py: DATABASE_URL
- Backend\tests\test_n8n_zero_push_workflow.py: replyToken, test_status_and_result_replies_use_current_interaction_reply_token
- Backend\tests\adapters\test_google_maps_crawler.py: api_key
- Backend\tests\api\test_business.py: api_key, BI_RMP_INTERNAL_API_KEY
- Backend\tests\api\test_client_messages_log.py: BI_RMP_INTERNAL_API_KEY
- Backend\tests\api\test_liff_registration.py: get_liff_token_verifier, id_token, LiffTokenVerifier, test_liff_token_verifier_posts_token_and_channel_id, token, tokens
- Backend\tests\api\test_line_registration_notification.py: channel_access_token, test_registration_notification_skips_without_token, token
- database\migrations\20260709_set_taipei_timezone.sql: service_role
- docs\design\line_rich_menu.png: itstTokens
- docs\design\Schema_overview.png: itstTokens
- docs\dev-spec\line-reputation-summary.md: token
- docs\dev-spec\line-rich-menu-guide.md: LINE_CHANNEL_ACCESS_TOKEN
- docs\dev-spec\n8n-line-integration.md: LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, N8N_DB_PASSWORD, password, reply_token, secret, secrets, token, tokens
- docs\dev-spec\requirements-spec.md: Token
- docs\integration\phase-1-report.md: secret
- docs\integration\phase-2-report.md: api_key, BI_RMP_INTERNAL_API_KEY, bi_rmp_local_searxng_secret_key_string, channel_access_token, DATABASE_URL, database_url, DB_POSTGRESDB_PASSWORD, GEMINI_API_KEY, get_liff_token_verifier, get_token, getIDToken, GOOGLE_MAPS_MORE_TOKENS, GOOGLE_MAPS_RESTRICTED_TEXT_TOKENS, GOOGLE_MAPS_REVIEWS_TOKENS, id_token, idToken, itstTokens, LiffTokenVerifier, LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, LINE_ID_TOKEN_VERIFY_URL, MORE_TOKENS, N8N_DB_PASSWORD, password, POSTGRES_PASSWORD, reply_token, replyToken, RESTRICTED_TEXT_TOKENS, REVIEWS_TOKENS, Secret, secret, secret_key, secrets, service_role, SUPABASE_SERVICE_ROLE_KEY, test_liff_token_verifier_posts_token_and_channel_id, test_registration_notification_skips_without_token, test_status_and_result_replies_use_current_interaction_reply_token, THREADS_CAPTCHA_TOKENS, THREADS_LOGIN_TOKENS, THREADS_RESTRICTED_TOKENS, Token, token, token_match_ratio, tokens, verify_internal_api_key, x_bi_rmp_api_key
- examples\litellm_example.py: api_key, GEMINI_API_KEY
- Frontend\register\index.html: getIDToken, id_token, idToken
- infra\n8n\docker-compose.yml: BI_RMP_INTERNAL_API_KEY, DB_POSTGRESDB_PASSWORD, LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, N8N_DB_PASSWORD, password, POSTGRES_PASSWORD
- infra\n8n\workflows\reputation-optimization-flow.json: BI_RMP_INTERNAL_API_KEY, LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, replyToken, secret, token
- infra\searxng\settings.yml: bi_rmp_local_searxng_secret_key_string, Secret, secret_key, tokens

## Warnings

- YAML validation skipped because PyYAML is not installed; no packages were installed.
- pytest skipped for safety; no runtime test execution performed.
- Secret scan found suspicious variable names; values were not printed.

## Fail Reasons

- None

## 結論

PASS WITH WARNINGS
