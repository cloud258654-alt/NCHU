# Dashboard Read API Contract

This document records the current Core API contract used by the Dashboard frontend integration work.

## Base URL

Local staging default:

```text
http://127.0.0.1:8000
```

Frontend code must obtain the API base URL from environment configuration. It must not hard-code Supabase REST URLs or service-role credentials.

## Endpoints

### Businesses

```http
GET /api/dashboard/businesses
```

Returns the business list available to the Dashboard.

### Summary

```http
GET /api/dashboard/summary
```

Query parameters:

- `business_id`: optional integer

### Reviews

```http
GET /api/dashboard/reviews
```

Query parameters:

- `page`: integer, 1 or greater
- `page_size`: integer, capped by the backend
- `business_id`: optional integer
- `platform`: optional string

The current API does not define `date_from`, `date_to`, or `sort` filters. Add those in a separate enhancement phase if the product requires them.

### Single Review

```http
GET /api/dashboard/reviews/{review_id}
```

Path parameters:

- `review_id`: integer

Expected behavior:

- Existing review: `200`
- Missing review: `404`
- Non-integer ID: request validation error before repository access

## Method Policy

Dashboard endpoints are read-only. The Dashboard API must not expose POST, PUT, PATCH, or DELETE methods.

## Frontend Requirements

The Dashboard frontend should cover these states:

- API loading
- Empty result state
- `503` backend unavailable state
- Pagination
- Platform filter
- Business filter
- Review detail `404`

Network requests should go only to the Core API base URL. Direct requests to `supabase.co/rest/v1`, `/api/supabase-query`, or frontend use of `DATABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` are not allowed.
