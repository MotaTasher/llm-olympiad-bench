# Scoring auth

Flask scoring-сайт полностью закрыт авторизацией. Без входа доступны только
`/login` и необходимые Flask static-ресурсы. Публичной регистрации нет; все
созданные аккаунты пока равноправны и считаются ревьюверами.

## Хранилище

Пользователи лежат в локальной SQLite DB:

```text
instance/scorer-auth.sqlite3
```

Путь можно переопределить:

```env
SCORER_AUTH_DB=/absolute/path/to/scorer-auth.sqlite3
```

База создаётся автоматически, но пользователи автоматически не создаются. Если
пользователей нет, войти не может никто. Auth DB содержит password hashes и не
должна попадать в Git, архивы или публичные бэкапы.

## Session secret

На сервере обязательно задайте стабильный приватный ключ:

```env
SCORER_SECRET_KEY=...
```

Сгенерировать шаблон значения:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Для локальной разработки без `SCORER_SECRET_KEY` приложение создаёт временный
ключ на процесс и выводит предупреждение без значения ключа. После перезапуска
такие сессии сбрасываются.

## Управление пользователями

Команды выполняются из корня репозитория:

```bash
flask --app scoring.app user create <username>
flask --app scoring.app user reset-password <username>
flask --app scoring.app user disable <username>
flask --app scoring.app user enable <username>
flask --app scoring.app user list
```

`username` задаёт оператор с терминальным доступом. Разрешены латинские буквы,
цифры, `.`, `_` и `-`, длина от 3 до 64 символов; пробелы по краям
отбрасываются, сравнение не зависит от регистра.

Администратор не задаёт пароль вручную. `create` и `reset-password` генерируют
пароль через `secrets.token_urlsafe(32)`, сохраняют только hash и показывают
plaintext-пароль в терминале один раз:

```text
User created: reviewer-01
Password: <generated password>
Save this password now. It will not be shown again.
```

Передайте пароль пользователю через отдельный защищённый канал или менеджер
паролей. Если пароль утрачен, посмотреть его нельзя; используйте
`reset-password`. Команда `disable` отзывает доступ, `enable` возвращает
возможность входа без смены пароля. Удаление пользователей через CLI сейчас не
реализовано.

`user list` показывает только username, active/disabled, created_at и
updated_at. Password hash не выводится.

## Cookies and deployment

Сессии используют Flask cookie с:

```env
SCORER_COOKIE_SECURE=1
SCORER_SESSION_HOURS=12
```

`SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE=Lax`, срок сессии по
умолчанию 12 часов. На HTTPS-сервере задайте `SCORER_COOKIE_SECURE=1`.

Flask development server нельзя публиковать напрямую в интернет. Серверный
scoring-сайт должен работать за HTTPS reverse proxy. Будущий публичный
visitor-интерфейс сейчас не реализован; если он появится, его маршруты нужно
явно вынести из default-deny auth-правила.

## Backup

Перед обслуживанием сервера можно сделать резервную копию auth DB:

```bash
sqlite3 instance/scorer-auth.sqlite3 ".backup '/secure/backup/scorer-auth.sqlite3'"
```

Храните резервную копию как приватный файл: она содержит password hashes.
