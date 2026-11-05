# Урок 1. Що таке Docker: образ, контейнер, volume. n8n у Docker

## Мета
Після уроку ти запускаєш n8n у Docker однією командою і розумієш, чому дані не зникають після перезапуску.

## Теорія

### 1. Проблема, яку вирішує Docker
«У мене працює, а на сервері ні»: інша версія Node, Python чи бібліотек. Docker пакує програму разом з усім оточенням, тому вона працює однаково всюди.

### 2. Три головні поняття
| Поняття | Аналогія | Приклад |
|---|---|---|
| **Образ (image)** | Інсталятор, шаблон | `n8nio/n8n` |
| **Контейнер** | Запущена програма з цього шаблону | твій n8n, що працює |
| **Volume** | Зовнішній диск для контейнера | дані n8n: workflows, credentials |

**Важливо:** контейнер одноразовий. Його можна видалити і створити знову, наприклад при оновленні. Все, що не лежить у volume, **зникне**.

### 3. docker compose
Замість довгих команд опис усього в одному файлі `docker-compose.yml`. Запуск: `docker compose up -d`.

## Приклади

Встанови Docker Desktop (Windows) з docker.com. Перевірка:
```bash
docker --version
docker run hello-world
```

Файл `practice/n8n/docker-compose.yml`:
```yaml
services:
  n8n:
    image: docker.n8n.io/n8nio/n8n
    restart: unless-stopped
    ports:
      - "5678:5678"
    environment:
      - GENERIC_TIMEZONE=Europe/Kyiv
      - TZ=Europe/Kyiv
    volumes:
      - n8n_data:/home/node/.n8n

volumes:
  n8n_data:
```

Команди:
```bash
cd practice/n8n
docker compose up -d        # запустити у фоні
docker compose ps           # статус
docker compose logs -f n8n  # логи (Ctrl+C для виходу)
docker compose down         # зупинити (дані у volume лишаються)
docker compose pull && docker compose up -d   # оновити n8n
```
Відкрий http://localhost:5678.

## Практика

**Завдання 1.** Встанови Docker і запусти `hello-world`.

**Завдання 2.** Запусти n8n через docker compose. Створи простий workflow і збережи його.

**Завдання 3.** Зроби `docker compose down`, потім знову `up -d`. Workflow на місці? Поясни чому.

**Завдання 4 (експеримент).** Прибери з compose-файлу рядки `volumes`, перезапусти, створи workflow, зроби `down` і `up`. Що сталося? Поверни volume на місце.

## Контрольні запитання
1. Чим образ відрізняється від контейнера?
2. Навіщо volume і що буде без нього при оновленні n8n?
3. Що означає `"5678:5678"` у ports?
4. Як подивитись, чому контейнер не запускається?
5. Що робить `restart: unless-stopped` і чому це важливо на сервері клієнта?

<details>
<summary>Відповіді</summary>

1. Образ — це шаблон, контейнер — запущений екземпляр цього шаблону.
2. Для постійного зберігання даних. Без нього після пересоздання контейнера всі workflows і credentials зникнуть.
3. Порт 5678 комп'ютера (зліва) з'єднаний з портом 5678 всередині контейнера (справа).
4. `docker compose logs <назва сервісу>`.
5. Контейнер автоматично піднімається після падіння чи перезавантаження сервера. Інакше після ребуту VPS автоматизації клієнта стоятимуть.
</details>

## Що далі
Урок 2: n8n + Postgres разом у docker compose.
