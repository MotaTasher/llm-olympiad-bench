# Provider Balance Links

This file is an operator shortcut for checking remaining API money, credits,
usage and billing limits. It must not contain API keys, tokens, account IDs or
project-specific secrets.

Provider consoles move routes from time to time. If a direct billing link stops
opening, use the provider console root in the same row and navigate to
Billing, Usage, Credits or Balance.

| Provider | Console / balance | Usage / billing details | Pricing |
| --- | --- | --- | --- |
| OpenAI | [Billing overview](https://platform.openai.com/settings/organization/billing/overview) | [Usage](https://platform.openai.com/usage) | [API pricing](https://openai.com/api/pricing) |
| Anthropic | [Console billing](https://console.anthropic.com/settings/billing) | [Console usage](https://console.anthropic.com/settings/usage) | [Pricing](https://www.anthropic.com/pricing) |
| DeepSeek | [Platform](https://platform.deepseek.com/) | [API balance endpoint docs](https://api-docs.deepseek.com/ap`i/get-user-balance) | [Pricing](https://api-docs.deepseek.com/quick_start/pricing) |
| Gemini | [AI Studio billing](https://aistudio.google.com/billing) | [Google Cloud Billing](https://console.cloud.google.com/billing) | [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| GigaChat | [Sber Studio project](https://developers.sber.ru/studio/workspaces/my-space/get/gigachat-api) | [Balance endpoint in API collection](https://www.postman.com/salute-developers-7605/public/documentation/17b9yp0/gigachat-api) | [Tariffs](https://developers.sber.ru/docs/ru/gigachat/api/tariffs) |
| Grok / xAI | [xAI console](https://console.x.ai/) | [xAI console](https://console.x.ai/) | [Pricing](https://docs.x.ai/developers/pricing) |
| GLM / Z.AI | [Z.AI API billing](https://z.ai/manage-apikey/billing) | [Z.AI billing entrypoint](https://z.ai/model-api) | [Pricing docs](https://docs.z.ai/guides/overview/pricing) |
| YandexGPT | [Yandex Cloud Billing](https://console.cloud.yandex.com/billing) | [Usage details docs](https://yandex.cloud/en/docs/billing/operations/check-charges) | [Foundation Models pricing](https://yandex.cloud/ru/prices#foundation-models) |

## API Checks

- DeepSeek exposes `GET https://api.deepseek.com/user/balance` for current
  balance. Use it only with the account API key stored outside git.
- GigaChat exposes a balance endpoint in the public API collection. Use it only
  with runtime credentials from `models/gigachat/secrets/.env` or private
  environment variables.
- For the other active providers, prefer the web console as the source of truth
  for remaining credits, billing tier and spend controls.
