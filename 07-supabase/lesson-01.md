# Урок 1. Перший проєкт Supabase: таблиці, SQL Editor, REST API, ключі

## Мета
Після уроку ти маєш хмарну базу Postgres, створюєш у ній таблиці й записуєш дані через API. Це основа для пам'яті агентів і клієнтських CRM.

## Теорія

### 1. Що таке Supabase
Хмарний Postgres, до якого вже «прикручені»:
- **Table Editor**: таблиці як у Excel;
- **SQL Editor**: для запитів;
- **автоматичний REST API**: кожна таблиця одразу доступна через HTTP;
- **Auth, Storage, pgvector** (для RAG).

Безкоштовного тарифу вистачає для навчання і невеликих клієнтів. Зауваж, що неактивні безкоштовні проєкти Supabase ставить на паузу.

### 2. Два ключі: найважливіше в уроці
| Ключ | Де використовувати | Що може |
|---|---|---|
| **anon / publishable** | Публічні місця: сайт, форма | Тільки те, що дозволяють правила RLS |
| **service_role / secret** | **Тільки сервер**: n8n, твій бекенд | **Все**, в обхід усіх правил |

Секретний ключ на сайті чи у фронтенді означає, що будь-хто може прочитати й видалити всі дані клієнта.

### 3. RLS (Row Level Security)
Правила «хто які рядки бачить». Якщо таблиця доступна через API, RLS має бути **увімкнений**. Детально розберемо в уроці 3.

## Приклади

SQL Editor → новий запит:
```sql
create table leads (
  id bigint generated always as identity primary key,
  name text not null,
  phone text,
  source text,
  status text default 'new',
  created_at timestamptz default now()
);

alter table leads enable row level security;

insert into leads (name, phone, source)
values ('Олена', '+380501112233', 'instagram');

select * from leads;
```

Запис через REST API (Python, ключі з `.env`):
```python
import os, requests
from dotenv import load_dotenv
load_dotenv()

url = os.getenv("SUPABASE_URL") + "/rest/v1/leads"
key = os.getenv("SUPABASE_SECRET_KEY")   # тільки на сервері!
headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}
r = requests.post(url, json={"name": "Андрій", "source": "google"}, headers=headers, timeout=10)
print(r.status_code, r.json())
```

## Практика

**Завдання 1.** Зареєструйся на supabase.com і створи проєкт `learning`. Збережи пароль бази в менеджері паролів.

**Завдання 2.** Через SQL Editor створи таблицю `leads` з прикладу і додай 3 записи.

**Завдання 3.** Знайди в налаштуваннях проєкту (Project Settings → API) URL і обидва ключі. Поясни викладачу, який з них куди піде.

**Завдання 4.** Запиши новий lead через Python-скрипт або через ноду Supabase / HTTP Request у n8n. Перевір, що він з'явився в Table Editor.

## Контрольні запитання
1. Що дає Supabase понад «просто базу даних»?
2. Чим anon-ключ відрізняється від service_role (secret)?
3. Розробник вставив secret-ключ у JavaScript на сайті клієнта. Чим це загрожує?
4. Що таке RLS одним реченням?
5. Який тип колонки краще для дати створення заявки, і чому `default now()` зручний?

<details>
<summary>Відповіді</summary>

1. Автоматичний REST API, авторизацію, файлове сховище, векторний пошук і зручний веб-інтерфейс.
2. Anon публічний і обмежений правилами RLS. Service_role має повний доступ в обхід RLS і живе тільки на сервері.
3. Будь-хто відвідувач може прочитати, змінити або видалити всі дані. Ключ треба негайно перевипустити.
4. Правила на рівні бази, які визначають, хто які рядки може читати й змінювати.
5. `timestamptz` (дата й час з часовим поясом). `default now()` автоматично ставить час створення, і не треба передавати його з workflow.
</details>

## Що далі
Урок 2: підключення Supabase з n8n і Python.
