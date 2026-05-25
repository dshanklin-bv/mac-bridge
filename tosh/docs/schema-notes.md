# Tosh Schema Notes

Learnings about querying the bronze layer tables.

## Messages Query Pattern

To find messages from a contact by name:

```sql
-- Step 1: Find contact's phone numbers
SELECT c.first_name, c.last_name, p.phone_number
FROM bronze.apple_contacts c
JOIN bronze.apple_contact_phones p ON c.id = p.contact_id
WHERE LOWER(c.first_name) LIKE '%taylor%';

-- Step 2: Find handle IDs for those phone numbers
-- Note: handles.identifier contains the phone/email, NOT handles.handle_id
SELECT id, identifier FROM bronze.apple_handles
WHERE identifier LIKE '%5127841141%';

-- Step 3: Get messages using handle IDs
-- Note: messages.handle_id is INTEGER referencing handles.id
SELECT m.date_apple, m.text, m.is_from_me, h.identifier
FROM bronze.apple_messages m
JOIN bronze.apple_handles h ON m.handle_id = h.id
WHERE m.handle_id = ANY(ARRAY[123, 456])  -- handle IDs from step 2
ORDER BY m.date_apple DESC;
```

## Table Schemas

### bronze.apple_messages
| Column | Type | Notes |
|--------|------|-------|
| id | integer | PK |
| handle_id | integer | FK to apple_handles.id |
| chat_id | integer | FK to apple_chats |
| text | text | Message content (null for reactions/attachments) |
| date_apple | bigint | Apple timestamp |
| is_from_me | boolean | Direction |
| synced_at | timestamptz | When synced |

### bronze.apple_handles
| Column | Type | Notes |
|--------|------|-------|
| id | integer | PK |
| identifier | text | Phone number or email (NOT handle_id!) |
| service | text | iMessage, SMS, etc |

### bronze.apple_contacts
| Column | Type | Notes |
|--------|------|-------|
| id | integer | PK |
| first_name | text | |
| last_name | text | |

### bronze.apple_contact_phones
| Column | Type | Notes |
|--------|------|-------|
| id | integer | PK |
| contact_id | integer | FK to apple_contacts.id |
| phone_number | text | Phone number |
| label | text | mobile, home, etc |

## Gotchas

1. **handles.identifier vs handle_id** - The phone/email is in `identifier`, not `handle_id`
2. **messages.handle_id is INTEGER** - References handles.id, not the phone number
3. **Phone format varies** - Some have +1, some have dashes, some don't. Use LIKE with just digits.
4. **Reactions show as [attachment/reaction]** - text is null, check associated_message_guid
5. **date_apple is Apple epoch** - Seconds since 2001-01-01, not Unix epoch

## Example: Full Contact Search

```python
# Find messages from a person by name
phones = ["5127841141", "2139276653"]  # digits only

cur.execute("""
    SELECT id FROM bronze.apple_handles
    WHERE identifier LIKE ANY(
        SELECT '%' || unnest || '%' FROM unnest(%s::text[])
    )
""", (phones,))
handle_ids = [r[0] for r in cur.fetchall()]

cur.execute("""
    SELECT m.text, m.is_from_me, m.date_apple
    FROM bronze.apple_messages m
    WHERE m.handle_id = ANY(%s)
    ORDER BY m.date_apple DESC
""", (handle_ids,))
```
