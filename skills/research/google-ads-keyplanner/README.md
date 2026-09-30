# Webdelo Google Ads Key Planner — credentials

This skill uses the existing service account:

```text
webdelo@fedorov.iam.gserviceaccount.com
```

## Download the JSON separately

The service-account private-key JSON is secret material and is **not** stored in this skill, in Git, or in chat. Download it separately from Google Cloud Console only if you are authorized:

1. Go to **Google Cloud Console → IAM & Admin → Service Accounts**.
2. Select `webdelo@fedorov.iam.gserviceaccount.com`.
3. Open **Keys** → **Add key** → **Create new key** → **JSON**.
4. Save the download in a private local directory, for example `$HERMES_HOME/secrets/webdelo-google-ads.json`.
5. Restrict the file locally: `terminal(command="chmod 600 $HERMES_HOME/secrets/webdelo-google-ads.json", timeout=30)`.
6. Check that its `client_email` is exactly `webdelo@fedorov.iam.gserviceaccount.com`; never print the `private_key` field.

A key can be downloaded only at creation time. If an existing key is unavailable, create one only with authorization. Revoke obsolete or exposed keys in Google Cloud Console.

## Configure local environment

In the active Hermes profile's `$HERMES_HOME/.env`, set only the file path and account ID:

```dotenv
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/webdelo-google-ads.json
GOOGLE_ADS_CUSTOMER_ID=1234567890
```

`GOOGLE_ADS_CUSTOMER_ID` is the target 10-digit Google Ads account ID without hyphens.

## Google Ads permissions

The JSON key alone is insufficient. A Google Ads administrator must add the service account under **Admin → Access and security** for the target account or its manager account. Google Ads API also requires an eligible developer token for live Keyword Planner data. If requests fail, check account access, customer ID, token access level, and allowed Keyword Planner use before modifying the script.

## Existing implementation

The ready baseline is `$HERMES_HOME/google_ads_service_account_siding_metrics.py`. It uses the service-account JSON and queries `generateKeywordHistoricalMetrics`. Keep it unchanged; make task-specific copies for other seeds or geo/language settings.
