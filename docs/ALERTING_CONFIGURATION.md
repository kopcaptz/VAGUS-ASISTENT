# Alerting Configuration

## Key Alert Manager

`KeyAlertManager` is started from API lifespan when enabled in runtime config:

```yaml
monitoring:
  key_alerts:
    enabled: true
    interval_seconds: 21600
    expiring_days_threshold: 7
    throttle_seconds: 3600
    escalation_warnings: 3
    watch_interval_seconds: 5
    alerting_config_path: "configs/telegram_test.yaml"
```

## Supported Alert Conditions

- key expiring soon / expired
- key validation failures
- rotation required aggregate condition

## Severity Rules

- `INFO`: rotation required summary signal
- `WARNING`: non-critical key issues
- `CRITICAL`: expired keys or escalated repeated warnings

## Throttling And Escalation

- same `rule + key` alerts are throttled for 1 hour
- 3 repeated warnings for same `rule + key` are escalated to critical

## Notification Channels

Alert delivery reuses existing `AlertingService` channels:

- Telegram
- Email
- Webhook

Configure channels in the YAML referenced by `alerting_config_path`.
