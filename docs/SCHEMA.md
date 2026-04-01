# events.json Schema Reference

`dist/events.json` is the primary output of this project. It is a JSON array of structured drag racing event records extracted from track websites and event flyers via Claude AI vision.

The machine-readable contract is defined in [`dist/events.schema.json`](dist/events.schema.json) (JSON Schema draft-07).

---

## Top-Level Structure

`events.json` is an array of **Event** objects.

```json
[ { ...Event }, { ...Event }, ... ]
```

---

## Event

The root object for a single drag racing event.

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (UUID) | Yes | Unique identifier (UUID v4) |
| `title` | string | Yes | Full event name as shown on the flyer |
| `event_type` | string (enum) | Yes | Primary event type — see values below |
| `series` | string \| null | No | Sanctioning body or series (e.g. NHRA, IHRA) |
| `track` | Track | Yes | Track information |
| `dates` | DateRange | Yes | Event date(s) |
| `times` | EventTimes | No | Gate, registration, and race start times |
| `classes` | string[] | No | Racing classes listed on the flyer |
| `fees` | Fees | No | Entry and spectator fees |
| `contact` | Contact | No | Phone, email, and website |
| `confidence` | number (0–1) | Yes | Extraction confidence score |
| `unclear_fields` | string[] | No | Fields where extraction was uncertain |
| `notes` | string \| null | No | Additional flyer information |
| `flyers` | FlyerRef[] | Yes | Source flyers/listings for this event |
| `created_at` | string (ISO 8601) | Yes | Record creation timestamp (UTC) |
| `updated_at` | string (ISO 8601) | Yes | Record last-modified timestamp (UTC) |

### event_type values

| Value | Description |
|---|---|
| `bracket` | Bracket racing |
| `points_race` | Points series race |
| `test_n_tune` | Test and tune session |
| `no_prep` | No-prep / radial racing |
| `grudge` | Grudge racing |
| `specialty` | Specialty or invitational event |
| `test_day` | Private test day |
| `unknown` | Could not be determined |

---

## Track

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string \| null | No | Stable slug for the track (e.g. `texas-motorplex-tx`). Use this for filtering — reliable across name variations |
| `name` | string | Yes | Official track name |
| `city` | string \| null | No | City where the track is located |
| `state` | string \| null | No | Two-letter US state abbreviation (e.g. `TX`) |

---

## DateRange

Dates are in `YYYY-MM-DD` format.

| Field | Type | Required | Description |
|---|---|---|---|
| `start` | string (date) | Yes | Event start date |
| `end` | string \| null | No | Event end date. Null for single-day events |

---

## EventTimes

All times are in 24-hour `HH:MM` format. All fields are null if not specified on the flyer.

| Field | Type | Description |
|---|---|---|
| `gates_open` | string \| null | Time gates open |
| `registration_opens` | string \| null | Registration open time |
| `race_start` | string \| null | First round start time |

---

## Fees

Fee values are raw strings as printed on the flyer — they are **not normalized** to a numeric type. Consumers should parse as needed.

| Field | Type | Description |
|---|---|---|
| `entry` | string \| null | Entry fee (e.g. `"$60/class"`, `"$100 per car"`) |
| `spectator` | string \| null | Spectator admission (e.g. `"$10"`) |

---

## Contact

| Field | Type | Description |
|---|---|---|
| `phone` | string \| null | Contact phone number |
| `email` | string \| null | Contact email address |
| `website` | string \| null | Event or track website URL |

---

## FlyerRef

Tracks the source material that contributed to an event record. An event may have multiple entries if the same event appeared across more than one source.

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | string | Yes | Flyer image filename, or source URL for text listings |
| `phash` | string \| null | No | Perceptual hash used for duplicate detection. Null for text listings |
| `processed_at` | string (ISO 8601) | Yes | Timestamp when this source was processed (UTC) |

---

## Confidence Score

The `confidence` field (0.0–1.0) reflects how clearly the source material presented the data.

| Range | Interpretation |
|---|---|
| 0.9–1.0 | High confidence — data is clearly legible |
| 0.7–0.9 | Good confidence — minor ambiguities |
| 0.5–0.7 | Moderate — some fields may be inaccurate |
| < 0.5 | Low — treat with caution; manual review recommended |

Fields that were specifically uncertain are listed in `unclear_fields`.

---

## Example Record

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Spring Bracket Classic",
  "event_type": "bracket",
  "series": null,
  "track": {
    "id": "texas-motorplex-tx",
    "name": "Texas Motorplex",
    "city": "Ennis",
    "state": "TX"
  },
  "dates": {
    "start": "2026-05-10",
    "end": "2026-05-11"
  },
  "times": {
    "gates_open": "07:00",
    "registration_opens": "08:00",
    "race_start": "10:00"
  },
  "classes": ["Super Pro", "Pro", "Sportsman", "Street"],
  "fees": {
    "entry": "$60/class",
    "spectator": "$15"
  },
  "contact": {
    "phone": "972-878-2641",
    "email": null,
    "website": "https://texasmotorplex.com"
  },
  "confidence": 0.94,
  "unclear_fields": [],
  "notes": null,
  "flyers": [
    {
      "file": "spring-bracket-classic-a1b2c3d4.jpg",
      "phash": "f3a1b2c3d4e5f6a7",
      "processed_at": "2026-03-31T12:00:00Z"
    }
  ],
  "created_at": "2026-03-31T12:00:00Z",
  "updated_at": "2026-03-31T12:00:00Z"
}
```
