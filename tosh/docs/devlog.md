
## [feature] 2026-01-14 21:52

Built and deployed the **tosh MCP server** - a FastMCP-based Model Context Protocol server that exposes Mac sync data to Claude.

### Tools Implemented (9 total)

| Tool | Purpose |
|------|---------|
| `photo_stats` | Synced/pending/iCloud counts |
| `photo_progress` | Date range covered, today's stats |
| `photo_breakdown` | Remaining by month/year |
| `send_to_reeves` | Send message to reeves agent |
| `read_from_reeves` | Read messages from reeves |
| `search_messages` | Find iMessages by contact name |
| `search_contacts` | Lookup contact info |
| `daemon_status` | Check daemon running, last cycle |
| `add_devlog` | This tool! Logs notes to docs |

### Key Files
- `tosh/mcp/server.py` - FastMCP server implementation
- `tosh/mcp/run.sh` - Wrapper script for cwd handling
- Registered via `claude mcp add --scope user tosh`

### Why This Matters
Before: Claude had to write raw SQL, fumble through schema discovery, guess column names.
After: Structured tools with clean outputs. "How's photos?" → instant stats.

### Schema Learnings Captured
Also documented the bronze layer schema gotchas in `tosh/docs/schema-notes.md`:
- `handles.identifier` (not `handle_id`) contains phone/email
- `messages.handle_id` is INTEGER FK to `handles.id`
- Phone formats vary - use LIKE with digits only

This is how agents should work - clean interfaces, not raw database fumbling.

## [feature] 2026-01-14 22:02 - Devlog Tools Complete

Added `read_devlog` and `search_devlog` tools to the MCP server. Also added optional `title` parameter to `add_devlog` for better organization.

Now have 11 tools total in the tosh MCP server.

## [feature] 2026-01-14 23:37 - Devlog API Finalized

Refactored devlog tools for better discoverability and consistency:

- `devlog_list(limit)` - Browse recent headers + IDs
- `devlog_read(entry_id)` - Fetch full content by ID
- `devlog_search(query)` - Search, returns full matches
- `devlog_add(content, title, category)` - Add with auto-timestamp

Prefix pattern (`devlog_*`) groups related tools together. IDs are stable (index from start of file).

## [research] 2026-01-15 04:28 - Photo Processing MCP Server - Research & Architecture

## Photo Processing MCP Server - Comprehensive Research

### Overview
Planning an MCP server to classify iPhone photos by type and route them to appropriate processing pipelines, converting unstructured image data into structured data.

---

## 20 Most Common iPhone Photo Types

### People & Social
1. **Selfies** - front camera, single person, often close-up
2. **Group photos** - multiple people, social gatherings
3. **Portraits** - intentional portrait mode, bokeh background
4. **Kids/Family** - children, family moments, candid

### Documents & Text
5. **Screenshots** - app screens, conversations, settings
6. **Documents** - receipts, bills, paperwork, contracts
7. **Whiteboard/Notes** - meeting notes, handwritten text
8. **Business cards** - contact info capture

### Food & Lifestyle
9. **Food photos** - meals, restaurants, cooking
10. **Product photos** - items for sale, purchases, packaging

### Places & Travel
11. **Landscapes** - nature, scenery, wide shots
12. **Architecture** - buildings, interiors, real estate
13. **Travel/Tourism** - landmarks, vacation spots
14. **Street scenes** - urban, city life

### Utility & Reference
15. **QR codes/Barcodes** - scanning for info
16. **Parking/Location** - "where I parked", meeting spots
17. **Labels/Instructions** - product info, how-to references
18. **ID/Cards** - insurance cards, IDs, membership cards

### Creative & Misc
19. **Pets/Animals** - dogs, cats, wildlife
20. **Memes/Social shares** - downloaded images, screenshots from social

---

## Processing Pipelines by Photo Type

### 1. Selfies
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Face Detection | MTCNN, RetinaFace, MediaPipe Face | Bounding boxes, landmarks |
| 2. Face Alignment | Affine transformation using eye/nose landmarks | Normalized face crop |
| 3. Face Embedding | ArcFace, FaceNet, InsightFace | 512-dim vector for identity |
| 4. Attribute Detection | DEX (age), FairFace (gender/ethnicity) | Age, gender, expression |
| 5. Quality Assessment | BRISQUE, face blur detection, lighting analysis | Quality score, usability rating |

**Structured output:** `{person_id, age_estimate, expression, quality_score, lighting, is_primary_face}`

---

### 2. Group Photos
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Multi-face Detection | RetinaFace, YOLO-Face | All face bounding boxes |
| 2. Face Clustering | DBSCAN on face embeddings | Person groups across photos |
| 3. Pose Estimation | MediaPipe Pose, OpenPose | Body positions, arrangement |
| 4. Scene Context | CLIP, Places365 | Event type (party, wedding, etc.) |
| 5. Social Graph Analysis | Proximity + co-occurrence frequency | Relationship strength scores |

**Structured output:** `{people: [{id, position, is_smiling}], event_type, group_size, occasion_guess}`

---

### 3. Portraits (Portrait Mode)
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Depth Map Extraction | Apple depth data from HEIC, or MiDaS | Depth layers |
| 2. Subject Segmentation | U²-Net, MODNet, Segment Anything | Foreground mask |
| 3. Face Analysis | Same as Selfies pipeline | Identity + attributes |
| 4. Bokeh Quality Assessment | Edge sharpness analysis, artifact detection | Portrait quality score |
| 5. Composition Analysis | Rule of thirds, golden ratio alignment | Composition score |

**Structured output:** `{subject_id, depth_quality, bokeh_strength, composition_score, background_type}`

---

### 4. Kids/Family
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Face Detection + Age | RetinaFace → DEX/MiVOLO age estimation | Faces with age ranges |
| 2. Child Detection | Age threshold (<18) + body proportion analysis | Is_child boolean |
| 3. Activity Recognition | Video/image action recognition (SlowFast, I3D) | Activity type |
| 4. Safety/Privacy Flag | Child face + public location = flag | Privacy sensitivity score |
| 5. Milestone Detection | CLIP with milestone prompts (first steps, birthday) | Event classification |

**Structured output:** `{children: [{age_range, activity}], adults: [], milestone_type, privacy_level}`

---

### 5. Screenshots
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Screenshot Detection | Aspect ratio + status bar detection + uniform edges | Is_screenshot confidence |
| 2. App Classification | Icon/UI pattern matching, CLIP | App name (Messages, Safari, etc.) |
| 3. Text Extraction | PaddleOCR, EasyOCR, Apple Vision | All text with bounding boxes |
| 4. Layout Analysis | LayoutLMv3, document segmentation | UI regions (header, content, nav) |
| 5. Content Classification | NLP on extracted text | Topic, sensitivity (passwords, PII) |

**Structured output:** `{app_name, text_content, contains_pii, topic, ui_regions[]}`

---

### 6. Documents
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Document Detection | Edge detection + perspective transform | Cropped, deskewed document |
| 2. Binarization | Adaptive thresholding, SauvolaNet | Clean black/white image |
| 3. OCR | Tesseract, PaddleOCR, DocTR | Full text extraction |
| 4. Document Classification | LayoutLMv3, Donut | Type (receipt, invoice, form) |
| 5. Key-Value Extraction | Form understanding models, regex patterns | Structured fields |

**Structured output:** `{doc_type, date, amounts[], vendor, line_items[], raw_text}`

---

### 7. Whiteboard/Notes
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Whiteboard Detection | Color segmentation (white/green board) | Board boundaries |
| 2. Perspective Correction | Homography estimation, OpenCV | Rectified image |
| 3. Stroke Enhancement | Contrast stretching, marker color boosting | Enhanced strokes |
| 4. Handwriting OCR | TrOCR, Google Cloud Vision HTR | Transcribed text |
| 5. Diagram Detection | Object detection for shapes, arrows, boxes | Diagram elements |

**Structured output:** `{transcribed_text, diagrams: [{type, connections}], keywords[], action_items[]}`

---

### 8. Business Cards
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Card Detection | Rectangle detection, aspect ratio filter | Card crop |
| 2. OCR | PaddleOCR with multi-language support | All text |
| 3. NER (Named Entity Recognition) | SpaCy, fine-tuned BERT | Name, company, title |
| 4. Contact Field Extraction | Regex + NER for phone, email, address | Structured contact |
| 5. Logo Detection | YOLO + logo embedding matching | Company identification |

**Structured output:** `{name, title, company, phone, email, address, website, linkedin}`

---

### 9. Food Photos
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Food Detection | YOLO trained on Food-101, Nutrition5k | Food bounding boxes |
| 2. Food Classification | EfficientNet on Food-101, im2recipe | Dish names |
| 3. Portion Estimation | Depth estimation + reference object | Serving size |
| 4. Nutrition Estimation | Food→nutrition lookup, calorie estimation models | Nutritional info |
| 5. Restaurant Detection | EXIF location + Google Places API | Venue info |

**Structured output:** `{dishes: [{name, portion, calories}], restaurant, cuisine_type, meal_type}`

---

### 10. Product Photos
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Object Detection | YOLO, Faster R-CNN | Product bounding boxes |
| 2. Product Recognition | Google Lens API, Amazon Rekognition | Product ID, brand |
| 3. Barcode/UPC Detection | ZBar, pyzbar | UPC codes |
| 4. Price Tag OCR | OCR + currency regex | Price extraction |
| 5. Condition Assessment | Fine-grained classification (new/used/damaged) | Condition score |

**Structured output:** `{product_name, brand, upc, price, condition, category, purchase_url}`

---

### 11. Landscapes
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Scene Classification | Places365, CLIP | Scene type (beach, mountain, etc.) |
| 2. Semantic Segmentation | DeepLabV3, SegFormer | Sky, water, vegetation, terrain |
| 3. Weather Detection | WeatherNet, sky color analysis | Weather conditions |
| 4. Time of Day | Sun position, color temperature | Golden hour, sunset, etc. |
| 5. Aesthetic Scoring | NIMA, TANet | Beauty/composition score |

**Structured output:** `{scene_type, weather, time_of_day, seasons, aesthetic_score, dominant_colors[]}`

---

### 12. Architecture
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Building Detection | Mask R-CNN trained on buildings | Building masks |
| 2. Architectural Style | Fine-tuned classifier (Gothic, Modern, etc.) | Style classification |
| 3. Perspective Analysis | Vanishing point detection, line analysis | Composition type |
| 4. Interior/Exterior | Binary classification | Location context |
| 5. Real Estate Features | Room type detection, amenity recognition | Property features |

**Structured output:** `{style, building_type, interior_exterior, rooms[], features[], year_estimate}`

---

### 13. Travel/Tourism
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Landmark Recognition | Google Landmark Recognition, CLIP | Landmark name |
| 2. Geolocation | EXIF GPS + reverse geocoding | Location details |
| 3. Tourist Activity | Activity classification | Activity type |
| 4. Crowd Density | People counting models | Crowdedness score |
| 5. Best-of Detection | Aesthetic score + landmark clarity | Album highlight candidate |

**Structured output:** `{landmark, city, country, activity, crowd_level, is_highlight, visit_date}`

---

### 14. Street Scenes
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Scene Segmentation | Cityscapes-trained models | Road, sidewalk, buildings, sky |
| 2. Object Detection | YOLO (vehicles, pedestrians, signs) | Scene objects |
| 3. Text/Sign OCR | Scene text detection (CRAFT + OCR) | Street names, store names |
| 4. Urban Context | Places365 | Neighborhood type |
| 5. Time/Weather | Lighting + sky analysis | Conditions |

**Structured output:** `{location_type, objects[], signs_text[], businesses[], time_of_day, weather}`

---

### 15. QR Codes/Barcodes
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Code Detection | pyzbar, ZXing, OpenCV | Code location + type |
| 2. Code Decoding | Type-specific decoder | Raw data |
| 3. URL Expansion | HTTP HEAD request for redirects | Final destination |
| 4. Content Classification | URL/text pattern matching | Code purpose (URL, WiFi, vCard) |
| 5. Safety Check | URL reputation API | Malicious link detection |

**Structured output:** `{code_type, raw_data, decoded_content, purpose, is_safe, expiry_date}`

---

### 16. Parking/Location
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Parking Context | Scene classification (garage, lot, street) | Parking type |
| 2. Level/Zone Detection | OCR for signs (P2, Zone B) | Location markers |
| 3. Vehicle Detection | YOLO for nearby cars | Reference vehicles |
| 4. Landmark Extraction | Distinctive feature detection | Navigation aids |
| 5. GPS + Timestamp | EXIF extraction | Precise location + time |

**Structured output:** `{parking_type, level, zone, gps, timestamp, landmarks[], auto_delete_after}`

---

### 17. Labels/Instructions
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Text Detection | CRAFT, DBNet | Text regions |
| 2. OCR | Multi-language OCR | All text |
| 3. Structured Extraction | Regex for dosage, ingredients, warnings | Key fields |
| 4. Category Classification | Product type from text | Label type |
| 5. Instruction Parsing | NLP for numbered steps | Action items |

**Structured output:** `{product_name, category, ingredients[], instructions[], warnings[], dosage}`

---

### 18. ID/Cards
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Card Type Detection | Template matching, aspect ratio | ID type |
| 2. MRZ Detection | MRZ-specific detection for passports | Machine-readable zone |
| 3. Field Extraction | ID-specific OCR models | Name, DOB, ID number |
| 4. Photo Extraction | Face detection on ID | ID photo crop |
| 5. Privacy Flagging | Auto-flag as sensitive | Security metadata |

**Structured output:** `{card_type, name, id_number, expiry, [ENCRYPTED], privacy_level: "high"}`

---

### 19. Pets/Animals
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Animal Detection | YOLO trained on animals | Animal bounding boxes |
| 2. Species Classification | iNaturalist model, Stanford Dogs/Cats | Species/breed |
| 3. Pet Identity | Pet face embedding (PetFace) | Pet ID for your pets |
| 4. Activity Detection | Action recognition | Playing, sleeping, eating |
| 5. Cuteness Scoring | Aesthetic + engagement prediction | Shareability score |

**Structured output:** `{species, breed, pet_id, activity, cuteness_score, is_your_pet}`

---

### 20. Memes/Social Shares
| Step | Tool/Method | Output |
|------|-------------|--------|
| 1. Meme Detection | Template matching, text overlay detection | Is_meme confidence |
| 2. Template Recognition | Meme template database matching | Meme template name |
| 3. Text Extraction | Impact font OCR | Caption text |
| 4. Sentiment Analysis | NLP on extracted text | Humor type, sentiment |
| 5. Originality Check | Reverse image search hash | Is_original, source |

**Structured output:** `{is_meme, template, caption_text, sentiment, source_url, is_original}`

---

## Common Interstitial Algorithms (Used Across Types)

| Algorithm | Purpose | Used In |
|-----------|---------|---------|
| **EXIF Parser** | Extract metadata (GPS, time, camera) | All types |
| **Image Orientation** | Auto-rotate based on EXIF | All types |
| **Denoising** | Reduce noise for better OCR/detection | Documents, low-light |
| **Super Resolution** | Enhance low-res for better extraction | Old photos, zoomed |
| **Color Correction** | Normalize lighting | Documents, food |
| **Perspective Transform** | Deskew documents/cards | Documents, whiteboards, IDs |
| **Face Embedding** | Identity vector for clustering | All people photos |
| **CLIP Embedding** | General semantic understanding | Classification fallback |

---

## Processing Implications Summary

- **OCR needed**: Documents, screenshots, whiteboard, business cards, labels
- **Face detection**: Selfies, portraits, group photos, kids
- **Location/EXIF important**: Travel, parking, landscapes
- **Should NOT sync to cloud**: IDs, sensitive documents
- **Auto-delete candidates**: Screenshots, parking spots, QR codes

---

## Key Models & Libraries to Evaluate

### Face Processing
- MTCNN, RetinaFace, MediaPipe Face (detection)
- ArcFace, FaceNet, InsightFace (embeddings)
- DEX, MiVOLO (age estimation)

### OCR
- PaddleOCR, EasyOCR, Tesseract, DocTR
- TrOCR (handwriting)
- CRAFT, DBNet (text detection)

### Scene Understanding
- CLIP (general semantic)
- Places365 (scene classification)
- DeepLabV3, SegFormer (segmentation)

### Object Detection
- YOLOv8, Faster R-CNN
- Segment Anything (SAM)

### Document Understanding
- LayoutLMv3, Donut (document AI)
- pyzbar, ZXing (barcodes)

---

## Next Steps
1. Design MCP server architecture with classifier → router → processor pattern
2. Evaluate which models can run locally vs need API calls
3. Define structured output schemas for each type
4. Build initial classifier to route photos to correct pipeline
5. Implement highest-value pipelines first (documents, screenshots, people)

## [feature] 2026-01-15 05:24 - Ojo Photo Context Extraction API - Complete Architecture PRD

# Ojo - Photo Context Extraction API
## Comprehensive Product Requirements Document

**Project Name:** Ojo (Spanish for "eye")
**Location:** ~/repos-personal/ojo/
**Type:** FastAPI REST API + MCP Server wrapper

---

## Executive Summary

Local-first, privacy-focused Photo Context Extraction API that extracts maximum structured context from photos using **80+ algorithms across 4 versions**. Provides semantic search, face recognition, and structured queries through FastAPI REST API with MCP server wrapper for Claude integration.

### Key Architecture Decisions
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Project Type | FastAPI REST + MCP wrapper | Flexibility for CLI, API, and Claude integration |
| Photo Sources | Local dirs + iCloud Photos | Configurable via osxphotos |
| Storage | SQLite + sqlite-vec | Local-first, portable, no cloud dependency |
| Processing | Tiered (Quick/Standard/Deep) | Resource-aware, on-demand depth |

---

## ALGORITHM TIERS (80 Algorithms Across 4 Versions)

### TIER 1: v1.0 - Essential Context (20 algorithms)
*Target: < 2s total per photo for standard tier*

| # | Algorithm | Category | Time | GPU | Output |
|---|-----------|----------|------|-----|--------|
| 1 | EXIF Metadata Extraction | Traditional | 10ms | No | dates, camera, GPS |
| 2 | Perceptual Hash (pHash) | Traditional | 20ms | No | duplicate detection |
| 3 | Color Palette Extraction | Traditional | 30ms | No | dominant colors, brightness |
| 4 | Image Quality Assessment | Traditional | 50ms | No | blur, exposure, noise |
| 5 | Orientation Detection | Traditional | 5ms | No | portrait/landscape |
| 6 | File Format Analysis | Traditional | 5ms | No | RAW, HEIC, JPEG |
| 7 | CLIP Embedding | ML/HF | 150ms | Yes | 768-dim semantic vector |
| 8 | BLIP-2 Caption | ML/HF | 500ms | Yes | natural language description |
| 9 | Face Detection (RetinaFace) | Detection | 100ms | Yes | bounding boxes, landmarks |
| 10 | Face Embedding (ArcFace) | Detection | 80ms | Yes | 512-dim face vectors |
| 11 | Object Detection (YOLOv8) | Detection | 120ms | Yes | 80 COCO classes |
| 12 | Scene Classification (Places365) | ML/HF | 100ms | Yes | 365 scene types |
| 13 | OCR (EasyOCR) | OCR | 500ms | Yes | text extraction |
| 14 | NSFW Detection | ML/HF | 100ms | Yes | content moderation |
| 15 | QR/Barcode Reading | Traditional | 50ms | No | decoded data |
| 16 | Document Detection | ML/HF | 80ms | Yes | is_document score |
| 17 | Person Count | Detection | 50ms | Yes | number of people |
| 18 | Aesthetic Score (NIMA) | ML/HF | 150ms | Yes | quality rating 1-10 |
| 19 | Timestamp Inference | Traditional | 10ms | No | from EXIF/filename |
| 20 | GPS/Location Extraction | Traditional | 10ms | No | coordinates, reverse geocode |

### TIER 2: v2.0 - Enhanced Context (20 algorithms)
*Adds emotional, environmental, and activity understanding*

| # | Algorithm | Category | Time | GPU | Output |
|---|-----------|----------|------|-----|--------|
| 21 | Emotion Detection | ML/HF | 100ms | Yes | facial emotions |
| 22 | Age Estimation | ML/HF | 80ms | Yes | approximate age |
| 23 | Gender Detection | ML/HF | 60ms | Yes | male/female/unknown |
| 24 | Landmark Recognition | ML/HF | 200ms | Yes | famous places |
| 25 | Food Recognition | ML/HF | 150ms | Yes | dishes, cuisines |
| 26 | Animal Detection | Detection | 100ms | Yes | species, breeds |
| 27 | Vehicle Detection | Detection | 100ms | Yes | cars, bikes, planes |
| 28 | Plant/Flower ID | ML/HF | 150ms | Yes | species identification |
| 29 | Weather Detection | ML/HF | 100ms | Yes | sunny, cloudy, rain |
| 30 | Indoor/Outdoor Classification | ML/HF | 80ms | Yes | environment type |
| 31 | Time of Day Estimation | ML/HF | 60ms | Yes | day/night/golden hour |
| 32 | Screenshot Detection | ML/HF | 80ms | Yes | platform identification |
| 33 | Meme Detection | ML/HF | 100ms | Yes | is_meme, format |
| 34 | Logo/Brand Detection | Detection | 150ms | Yes | company logos |
| 35 | Clothing Detection | Detection | 120ms | Yes | fashion items |
| 36 | Activity Recognition | ML/HF | 200ms | Yes | running, eating, etc. |
| 37 | Depth Estimation | ML/HF | 300ms | Yes | monocular depth map |
| 38 | Composition Analysis | Traditional | 50ms | No | rule of thirds, balance |
| 39 | Dominant Subject Detection | ML/HF | 100ms | Yes | main focus area |
| 40 | Semantic Segmentation | ML/HF | 400ms | Yes | pixel-level labels |

### TIER 3: v3.0 - Deep Context (20 algorithms)
*Adds relationship, event, and document understanding*

| # | Algorithm | Category | Time | GPU | Output |
|---|-----------|----------|------|-----|--------|
| 41 | Relationship Detection | Vision LLM | 2s | Yes | family groupings |
| 42 | Event Classification | Vision LLM | 1.5s | Yes | birthday, wedding |
| 43 | Document Type Classification | ML/HF | 150ms | Yes | receipt, ID, bill |
| 44 | Receipt Data Extraction | OCR+ | 800ms | Yes | amounts, vendors |
| 45 | Business Card Extraction | OCR+ | 500ms | Yes | contact info |
| 46 | Handwriting Recognition | OCR | 600ms | Yes | handwritten text |
| 47 | Art Style Classification | ML/HF | 200ms | Yes | photo vs painting |
| 48 | Music/Instrument Detection | Detection | 150ms | Yes | instruments visible |
| 49 | Sports Recognition | ML/HF | 150ms | Yes | type of sport |
| 50 | Travel Detection | ML/HF | 150ms | Yes | airport, tourist |
| 51 | Social Media Platform Detection | ML/HF | 100ms | Yes | source app |
| 52 | Photo Series Detection | Traditional | 30ms | No | burst, panorama |
| 53 | Before/After Detection | ML/HF | 200ms | Yes | comparison pairs |
| 54 | Collage Detection | ML/HF | 100ms | Yes | multiple images |
| 55 | Privacy Risk Assessment | ML/HF | 300ms | Yes | sensitive content |
| 56 | Memory Significance Scoring | Vision LLM | 1s | Yes | importance score |
| 57 | Similar Photo Clustering | Embedding | 100ms | No | visual grouping |
| 58 | Story/Narrative Detection | Vision LLM | 1.5s | Yes | photo sequences |
| 59 | Vehicle Make/Model Detection | ML/HF | 200ms | Yes | specific vehicles |
| 60 | Pet Breed Identification | ML/HF | 150ms | Yes | dog/cat breeds |

### TIER 4: v4.0 - Specialized Context (20 algorithms)
*Domain-specific and advanced analysis*

| # | Algorithm | Category | Time | GPU | Output |
|---|-----------|----------|------|-----|--------|
| 61 | Medical Image Detection | ML/HF | 200ms | Yes | X-rays, scans |
| 62 | Real Estate Photo Analysis | ML/HF | 300ms | Yes | room type |
| 63 | Product Photography Detection | ML/HF | 150ms | Yes | e-commerce |
| 64 | Scientific Image Analysis | ML/HF | 200ms | Yes | charts, diagrams |
| 65 | Map/Navigation Screenshot | OCR+ | 400ms | Yes | location data |
| 66 | Conversation Screenshot Analysis | OCR+ | 600ms | Yes | message extraction |
| 67 | Game Screenshot Detection | ML/HF | 150ms | Yes | game identification |
| 68 | Fashion Style Classification | ML/HF | 200ms | Yes | aesthetic type |
| 69 | Food Nutrition Estimation | ML/HF | 300ms | Yes | calorie estimate |
| 70 | Plant Health Assessment | ML/HF | 200ms | Yes | disease detection |
| 71 | Document Layout Analysis | ML/HF | 400ms | Yes | tables, forms |
| 72 | Signature Detection | Detection | 100ms | Yes | signature locations |
| 73 | Stamp/Seal Detection | Detection | 100ms | Yes | official marks |
| 74 | Damage Assessment | ML/HF | 200ms | Yes | scratches, tears |
| 75 | Forgery Detection | ML/HF | 500ms | Yes | manipulation signs |
| 76 | HDR Detection | Traditional | 30ms | No | dynamic range |
| 77 | Bokeh/DoF Analysis | Traditional | 50ms | No | depth of field |
| 78 | Motion Blur Analysis | Traditional | 40ms | No | blur direction |
| 79 | Noise Level Assessment | Traditional | 30ms | No | ISO noise |
| 80 | Compression Artifact Detection | Traditional | 40ms | No | JPEG artifacts |

---

## DIRECTORY STRUCTURE

```
~/repos-personal/ojo/
├── pyproject.toml
├── README.md
├── .env                              # API keys, config
├── src/ojo/
│   ├── __init__.py
│   ├── config.py                     # Settings management
│   │
│   ├── api/                          # FastAPI REST API
│   │   ├── __init__.py
│   │   ├── main.py                   # App factory, lifespan
│   │   ├── dependencies.py           # DI containers
│   │   └── routers/
│   │       ├── photos.py             # CRUD endpoints
│   │       ├── search.py             # Semantic search
│   │       ├── processing.py         # Job management
│   │       └── algorithms.py         # Algorithm info
│   │
│   ├── mcp/                          # MCP Server
│   │   ├── __init__.py
│   │   ├── server.py                 # MCP entry point
│   │   └── tools.py                  # Tool definitions
│   │
│   ├── core/                         # Business logic
│   │   ├── photo_service.py
│   │   ├── search_service.py
│   │   └── processing_service.py
│   │
│   ├── plugins/                      # Algorithm plugins
│   │   ├── __init__.py
│   │   ├── base.py                   # AlgorithmBase ABC
│   │   ├── registry.py               # Discovery & registration
│   │   └── impl/
│   │       ├── tier1/                # v1.0 algorithms
│   │       ├── tier2/                # v2.0 algorithms
│   │       ├── tier3/                # v3.0 algorithms
│   │       └── tier4/                # v4.0 algorithms
│   │
│   ├── models/                       # ML Model Management
│   │   ├── __init__.py
│   │   ├── manager.py                # Lazy loading, GPU management
│   │   └── loaders/                  # Per-model loaders
│   │
│   ├── sources/                      # Photo Source Adapters
│   │   ├── base.py
│   │   ├── local_directory.py
│   │   └── icloud_photos.py          # via osxphotos
│   │
│   ├── db/                           # Database Layer
│   │   ├── database.py               # Connection management
│   │   ├── schema.sql                # DDL
│   │   ├── models.py                 # SQLAlchemy/dataclass
│   │   └── vector_store.py           # sqlite-vec ops
│   │
│   ├── search/                       # Search Engine
│   │   ├── engine.py                 # Hybrid search
│   │   ├── ranking.py                # RRF, scoring
│   │   └── embeddings.py             # CLIP text encoder
│   │
│   ├── faces/                        # Face Recognition
│   │   ├── detection.py
│   │   ├── clustering.py             # HDBSCAN
│   │   └── recognition.py
│   │
│   └── workers/                      # Background Processing
│       ├── job_queue.py              # SQLite-based queue
│       └── processor.py              # Worker implementation
│
├── data/                             # Local data (gitignored)
│   ├── ojo.db                        # SQLite database
│   └── models/                       # Cached ML models
│
└── tests/
```

---

## DATABASE SCHEMA

```sql
-- Photos table
CREATE TABLE photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    file_hash TEXT NOT NULL,              -- SHA-256
    width INTEGER, height INTEGER,
    capture_date DATETIME,
    latitude REAL, longitude REAL,
    caption TEXT,                         -- AI-generated
    quality_score REAL,
    processing_tier TEXT DEFAULT 'none',  -- none/quick/standard/deep
    deleted_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Vector embeddings (sqlite-vec)
CREATE VIRTUAL TABLE vec_photo_clips USING vec0(
    photo_id INTEGER PRIMARY KEY,
    clip_embedding float[768]
);

CREATE VIRTUAL TABLE vec_face_embeddings USING vec0(
    face_id INTEGER PRIMARY KEY,
    face_embedding float[512]
);

-- Full-text search (FTS5)
CREATE VIRTUAL TABLE fts_photos USING fts5(
    caption, ocr_text, detected_objects,
    content='photos', content_rowid='id'
);

-- Detected objects
CREATE TABLE photo_objects (
    id INTEGER PRIMARY KEY,
    photo_id INTEGER REFERENCES photos(id),
    object_class TEXT NOT NULL,
    confidence REAL,
    bbox_x REAL, bbox_y REAL,
    bbox_width REAL, bbox_height REAL
);

-- Faces
CREATE TABLE faces (
    id INTEGER PRIMARY KEY,
    photo_id INTEGER REFERENCES photos(id),
    person_id INTEGER REFERENCES persons(id),
    bbox_x REAL, bbox_y REAL,
    bbox_width REAL, bbox_height REAL,
    confidence REAL,
    emotion TEXT, age_estimate INTEGER
);

-- Known persons (face clusters)
CREATE TABLE persons (
    id INTEGER PRIMARY KEY,
    name TEXT,
    face_count INTEGER DEFAULT 0,
    representative_face_id INTEGER
);

-- Processing queue
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    photo_id INTEGER REFERENCES photos(id),
    algorithm_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    last_error TEXT
);
```

---

## PLUGIN SYSTEM

### Base Class
```python
class AlgorithmBase(ABC):
    name: str = "base"
    version: int = 1
    tier: ProcessingTier = ProcessingTier.STANDARD
    required_models: List[str] = []

    @abstractmethod
    def process(self, image: Image, photo_id: str) -> AlgorithmResult:
        pass

@dataclass
class AlgorithmResult:
    data: dict                    # Algorithm output
    entities: List[dict] = []    # Extracted entities
    embedding: List[float] = None
    processing_time_ms: int = 0
    confidence: float = 1.0
```

### Registry Pattern
```python
@register_algorithm
class CLIPEmbeddingV1(AlgorithmBase):
    name = "clip_embedding"
    version = 1
    tier = ProcessingTier.STANDARD
    required_models = ["clip_vit_large"]
```

---

## SEARCH SYSTEM - HYBRID RRF

```sql
-- Reciprocal Rank Fusion combining semantic + text
WITH semantic_results AS (
    SELECT photo_id, distance,
           ROW_NUMBER() OVER (ORDER BY distance) as rank
    FROM vec_photo_clips
    WHERE clip_embedding MATCH :query_embedding
    LIMIT 200
),
text_results AS (
    SELECT rowid as photo_id, bm25(fts_photos) as score,
           ROW_NUMBER() OVER (ORDER BY bm25(fts_photos) DESC) as rank
    FROM fts_photos WHERE fts_photos MATCH :text_query
    LIMIT 200
)
SELECT photo_id,
       0.6 / (60.0 + s.rank) + 0.4 / (60.0 + t.rank) as rrf_score
FROM semantic_results s
FULL OUTER JOIN text_results t USING (photo_id)
ORDER BY rrf_score DESC;
```

---

## MCP TOOLS

```python
TOOLS = [
    Tool(name="ojo_search", description="Semantic photo search"),
    Tool(name="ojo_analyze", description="Get photo context"),
    Tool(name="ojo_find_similar", description="Find similar photos"),
    Tool(name="ojo_find_duplicates", description="Find duplicates"),
    Tool(name="ojo_search_faces", description="Find photos with person"),
    Tool(name="ojo_stats", description="Library statistics"),
    Tool(name="ojo_process", description="Queue photos for analysis"),
    Tool(name="ojo_import", description="Import from source"),
    Tool(name="ojo_algorithms", description="List available algorithms"),
]
```

---

## API ENDPOINTS

```
POST /api/v1/search              # Hybrid search
GET  /api/v1/photos/{id}         # Get photo context
GET  /api/v1/photos/{id}/similar # Similar photos
POST /api/v1/faces/search        # Face similarity search
GET  /api/v1/persons             # List known persons
GET  /api/v1/persons/{id}/photos # Photos with person
POST /api/v1/processing/batch    # Queue batch processing
GET  /api/v1/processing/stats    # Queue statistics
GET  /api/v1/algorithms          # List algorithms
```

---

## DEPENDENCIES

```toml
[project]
dependencies = [
    # Core
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "mcp>=1.0.0",
    "pydantic>=2.0.0",

    # Database
    "sqlite-vec>=0.1.0",

    # Image Processing
    "pillow>=10.0.0",
    "imagehash>=4.3.0",

    # ML Models
    "torch>=2.0.0",
    "transformers>=4.36.0",
    "sentence-transformers>=2.2.0",

    # Detection
    "ultralytics>=8.0.0",         # YOLOv8
    "retinaface-pytorch>=0.0.8",
    "deepface>=0.0.79",           # ArcFace

    # OCR
    "easyocr>=1.7.0",

    # Face Clustering
    "hdbscan>=0.8.0",

    # Photo Sources
    "osxphotos>=0.66.0",

    # Utilities
    "httpx>=0.25.0",
    "python-dotenv>=1.0.0",
]
```

---

## IMPLEMENTATION PHASES

### Phase 1: Foundation
- Project setup, pyproject.toml, directory structure
- SQLite schema with sqlite-vec and FTS5
- Plugin base class and registry
- Model manager with GPU/MPS detection

### Phase 2: Tier 1 Algorithms
- Traditional CV: EXIF, pHash, color, quality
- ML: CLIP embedding, BLIP-2 caption
- Detection: YOLOv8, RetinaFace, ArcFace
- OCR: EasyOCR integration

### Phase 3: Search & API
- Hybrid search engine (semantic + FTS5)
- FastAPI REST endpoints
- Face clustering with HDBSCAN
- MCP server wrapper

### Phase 4: Photo Sources
- Local directory scanner
- iCloud Photos via osxphotos
- Background job processor

### Phase 5: Tier 2-4
- Tier 2: Enhanced context algorithms
- Tier 3: Deep context with Vision LLMs
- Tier 4: Specialized domain algorithms

---

## CRITICAL FILES TO CREATE FIRST

1. `src/ojo/plugins/base.py` - Plugin architecture foundation
2. `src/ojo/plugins/registry.py` - Algorithm discovery and management
3. `src/ojo/models/manager.py` - GPU memory and model caching
4. `src/ojo/db/schema.sql` - Complete database DDL
5. `src/ojo/search/engine.py` - Hybrid search with RRF
6. `src/ojo/workers/job_queue.py` - Tiered processing queue
7. `src/ojo/mcp/tools.py` - MCP tool definitions
8. `src/ojo/api/main.py` - FastAPI application

## [feature] 2026-01-17 19:01 - Knox Project Complete

## Knox Secrets Vault - Full Stack Implementation

### Completed Components:
1. **Vault Schema** - Deployed to aic Supabase (`hrezmztjmvzzibfhvpyo`)
   - `secrets` schema with Supabase Vault integration
   - `access_log` table for audit trail
   - SECURITY DEFINER functions for secure access

2. **Knox MCP Server** (`/repos-aic/knox/knox-mcp/`)
   - `knox_list_secrets()` - List all secrets (names only)
   - `knox_get_secret(name, client_id)` - Get secret with audit logging
   - `knox_access_log()` - View access history
   - Configured in ~/.claude/settings.json with service_role key

3. **Frontend** (Next.js 15 + shadcn/ui)
   - Deployed to Vercel under AIC Holdings team
   - Project renamed from "frontend" to "knox"
   - Connected to GitHub repo `aic-holdings/knox`
   - Auto-deploy on main branch enabled

4. **Vercel MCP** - Added to Claude Code for deployment management
   - `claude mcp add --transport http vercel https://mcp.vercel.com --scope user`
   - OAuth authenticated

### Issues Encountered:
- Vercel CLI defaulted to personal team instead of AIC Holdings - fixed with `--scope aic-holdings-rhea-ai`
- Project rename not available via CLI - had to use dashboard
- GitHub connection requires Pro plan for private org repos (AIC Holdings has Pro)

### Next Steps:
- Fix deployment error (root directory config for monorepo)
- Test Knox MCP tools after Claude Code restart
- Add secrets to Knox vault for testing

## [feature] 2026-01-17 19:07 - Knox Session Complete - Full Stack Deployed

## Knox Secrets Vault - Session Summary

### What We Built Today:

**1. Vault Schema → aic Supabase**
- `secrets` schema with Supabase Vault extension
- `access_log` table for audit trail
- SECURITY DEFINER functions for secure access
- Deployed via SQL Editor (Supabase MCP had permission issues)

**2. Knox MCP Server**
- Built FastMCP server in Python
- Three tools: `knox_list_secrets`, `knox_get_secret`, `knox_access_log`
- Configured in ~/.claude/settings.json with service_role key
- Ready to test after Claude Code restart

**3. Frontend → Vercel**
- Deployed to AIC Holdings team (not personal)
- Project renamed from "frontend" to "knox"
- Connected to GitHub repo `aic-holdings/knox`
- Auto-deploy on main branch working
- Fixed monorepo build with root vercel.json

**4. Vercel MCP Added**
- `claude mcp add --transport http vercel https://mcp.vercel.com --scope user`
- OAuth authenticated
- Can now deploy/manage Vercel projects directly

### Key Learnings:
- Vercel CLI defaults to personal team - use `--scope` flag
- Monorepo builds need root vercel.json with `cd frontend && npm run build`
- Supabase MCP execute_sql has permission issues - use Dashboard SQL Editor
- Project rename only via Vercel Dashboard (no CLI/API)

### GitHub Project Updated:
- Knox Development: 10/14 issues complete
- Closed #7 (schema), #9 (MCP tools), #10 (Vercel)

### Remaining Work:
- #8: Migrate secrets from Infisical
- #12: RBAC user_roles table
- #13: Next.js 16 proxy migration
- #14: Jetta SSO integration

## [learning] 2026-01-17 19:11 - Knox Remaining Work - Task Order Analysis

## Knox Task Dependencies & Execution Order

### Dependency Graph:
```
#14 Jetta SSO ─────┐
                   ├──► #12 RBAC ──► Frontend fully functional
#8 Secrets migrate ┘

#13 Proxy migration (independent, tech debt)
```

### Recommended Order:

1. **#8 Migrate secrets from Infisical**
   - Knox MCP is ready NOW
   - Can populate vault immediately without frontend
   - Makes Knox useful for AI agents right away
   - No blockers

2. **#14 Jetta SSO integration**
   - Unblocks frontend login
   - Required for users to access Knox UI
   - Depends on Jetta SSO being configured in aic Supabase (already done - #11)

3. **#12 RBAC user_roles table**
   - Needs auth working to check roles
   - Depends on #14
   - Enables admin-only features

4. **#13 Next.js 16 proxy migration**
   - Tech debt cleanup
   - Middleware still works, just deprecated
   - Lowest priority, no functional impact

### Key Insight:
Start with backend work (#8) that doesn't depend on frontend auth. This makes Knox immediately valuable for MCP-based secret access while frontend auth is being set up.

## [feature] 2026-01-17 19:15 - Knox Vault Migration Complete

## Infisical → Knox Vault Migration

Successfully migrated all 11 secrets from Infisical to Knox vault.

### Secrets Migrated:
| Secret | Category |
|--------|----------|
| AUTHENTIK_API_TOKEN | Identity |
| OPENROUTER_API_KEY | AI/LLM |
| V0_API_KEY | AI/LLM |
| GITHUB_TOKEN | Dev Tools |
| ARTEMIS_MASTER_API_KEY | Artemis |
| CLIFF_ARTEMIS_API_KEY | Artemis |
| CAPTURES_ARTEMIS_API_KEY | Artemis |
| SPEACHES_ARTEMIS_API_KEY | Artemis |
| ARGUS_API_KEY | Monitoring |
| UPTIME_KUMA_USERNAME | Monitoring |
| UPTIME_KUMA_PASSWORD | Monitoring |

### Process:
1. Used Janus MCP to list and retrieve secrets from Infisical
2. Generated SQL migration script using `vault.create_secret()`
3. Ran script in Supabase Dashboard (MCP had permission issues)

### Knox Vault Total: 13 secrets
- 11 from Infisical
- 2 Supabase keys (already present)

### GitHub Issue #8: CLOSED

## [bug] 2026-01-17 19:17 - Knox Migration Mistake - Wrong Secrets Source

## Problem: Migrated Personal Secrets to AIC Project

### What Happened:
When asked to migrate secrets to Knox (AIC Holdings), I pulled secrets from Janus/Infisical - which is a **personal** project, not AIC.

### The Mistake:
- Janus MCP connects to personal Infisical instance
- Knox is for AIC Holdings organization
- I migrated 11 personal secrets into the AIC Knox vault
- Had to roll back with DELETE statements

### Secrets Incorrectly Added (then removed):
- AUTHENTIK_API_TOKEN (personal)
- OPENROUTER_API_KEY (personal)
- V0_API_KEY (personal)
- GITHUB_TOKEN (personal)
- ARTEMIS_* keys (personal)
- ARGUS_API_KEY (personal)
- UPTIME_KUMA_* (personal)

### Root Cause:
Didn't clarify the SOURCE of secrets before migration. Assumed Janus/Infisical was the AIC secrets store, but it's actually personal.

### Lesson Learned:
**Always verify the source system ownership before migrating data between projects.** Just because a tool is available (Janus MCP) doesn't mean it's the right source for the target project (Knox/AIC).

### Current State:
Knox vault cleaned - only contains 2 AIC Supabase keys.
GitHub issue #8 reopened - need to identify actual AIC secrets to migrate.

## [bug] 2026-01-23 01:22 - Apple Contacts Multi-Source Discovery

## Problem
Contacts sync was only returning 3 records when user has 4,781+ contacts.

## Root Cause
Apple Contacts stores data across MULTIPLE source databases, not just one:
- Main DB: `~/Library/Application Support/AddressBook/AddressBook-v22.abcddb` (only 3 records)
- Per-account DBs: `~/Library/Application Support/AddressBook/Sources/{UUID}/AddressBook-v22.abcddb`

Each account (iCloud, Google, Exchange, etc.) gets its own UUID folder with its own database.

## Discovery
```bash
find ~/Library -name "*.abcddb"
# Found 5 databases!

for db in ~/Library/Application\ Support/AddressBook/Sources/*/AddressBook-v22.abcddb; do
  sqlite3 "$db" "SELECT COUNT(*) FROM ZABCDRECORD;"
done
# 1358, 3249, 3, 171 = 4781 total
```

## Fix
Updated `contacts.py` to:
1. Scan all source directories
2. Create composite IDs (`{source_uuid}:{rowid}`) to avoid collisions
3. Truncate and reload on each sync (contacts change frequently)

## Lesson
Apple often shards local data by account/source. When syncing Apple data, always check for Sources/UUID patterns - the main database may be nearly empty while the real data lives in per-account subdirectories.

## Related
Same pattern likely applies to:
- Calendar (per-account .caldav files)
- Reminders
- Any iCloud-synced data

## [feature] 2026-01-23 16:16 - Queue-based async dietz refresh - replaced blocking triggers

## Problem
Position allocation inserts were timing out because the `tr_refresh_dietz_on_allocation` trigger synchronously ran a 30-60 second dietz refresh.

## Root Cause Investigation
- Found 55 orphaned pnl rows with malformed position_keys (pattern `|||`)
- Discovered dietz_daily was missing accounts xpb006160 and xpb006178 for Jan 20-22
- Entity NAV totals exceeded account NAV by ~$18M due to stale data

## Solution: Queue-based async refresh

### New Architecture
1. **Lightweight trigger** (`tr_queue_dietz_refresh`) - just inserts into `gold.dietz_refresh_queue` (5ms)
2. **Queue table** - stores pending refresh jobs with deduplication
3. **Processor function** (`fn_process_dietz_refresh_queue`) - picks up jobs and runs refreshes
4. **Edge function** (`dietz-refresh-listener`) - frontend can fire-and-forget to trigger immediate processing
5. **pg_cron fallback** - processes queue every minute as safety net

### Frontend Usage
```javascript
await supabase.from('position_allocations').insert(data)
// Fire-and-forget (async, user doesn't wait)
fetch(`${SUPABASE_URL}/functions/v1/dietz-refresh-listener`, {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}` }
})
```

### QA Checks Added to sable-cli pipeline
- Check 6: Missing accounts in dietz_daily
- Check 7: Entity vs account NAV mismatch (double-counting detection)

## Files Changed
- `supabase/migrations/20260123230000_disable_blocking_dietz_trigger.sql`
- `supabase/migrations/20260123235000_dietz_refresh_queue.sql`
- `supabase/migrations/20260124000000_instant_dietz_refresh.sql`
- `supabase/functions/dietz-refresh-listener/index.ts`
- `sable-cli/sable.js` (Phase 6b data integrity checks)

## Key Learnings
- pg_cron minimum interval is 1 minute
- Synchronous triggers on hot tables are dangerous for slow operations
- Queue + async processing pattern works well for deferred heavy work

## [feature] 2026-01-24 23:20 - Artemis Web Search Feature & Test Suite

# Artemis Web Search Feature

## What Was Added

### 1. OpenRouter Web Search Support
Added three ways to enable web search via Artemis API:

**Via convenience headers (recommended):**
```
X-Artemis-Web-Search: true
X-Artemis-Web-Results: 5  # optional, 1-10, default 5
```

**Via request body plugins array:**
```json
{"plugins": [{"id": "web", "max_results": 5}]}
```

**Via model suffix:**
```
model: "openai/gpt-4o:online"
```

### 2. Model Variant Normalization
`ProviderModelService._normalize_model_id()` strips OpenRouter variant suffixes:
- `:online` - Web search enabled
- `:thinking` - Extended reasoning
- `:extended` - Extended context
- `:free` - Free tier
- `:beta` - Beta models

Handles stacked suffixes like `openai/gpt-4o:online:thinking` → `openai/gpt-4o`

### 3. CLI Web Search
`artemis proxy test "query" --web --web-results 5`

Citations displayed from response annotations.

## Files Modified
- `app/routers/proxy_routes.py` - Added X-Artemis-Web-Search header processing
- `app/routers/guide.py` - Added web search docs to /api/agent-setup/configure
- `app/services/provider_model_service.py` - Added _normalize_model_id()
- `scripts/artemis_cli/cli.py` - Added --web flag to proxy test

## Test Files Added
- `tests/services/test_provider_model_service.py` - 23 tests for model service
- `tests/cli/test_proxy_commands.py` - CLI proxy command tests
- `tests/cli/test_models_commands.py` - CLI models command tests
- `tests/cli/test_whisper_commands.py` - CLI whisper command tests
- `tests/proxy/test_web_search.py` - Web search header processing tests
- `tests/conftest.py` - Added test_db fixture for async tests

## Dependencies Added
- `aiosqlite>=0.19.0` for async SQLite testing

## Citation Response Format
OpenRouter returns citations in message.annotations:
```json
{
  "annotations": [{
    "type": "url_citation",
    "url_citation": {
      "url": "https://example.com",
      "title": "Source Title"
    }
  }]
}
```

## [feature] 2026-01-25 11:46 - Mini-RAG Implementation - Persona Quality 95/100

## Watts Persona Mini-RAG Implementation

Successfully implemented mini-RAG system to fix "fortune cookie" persona problem.

### Problem Solved
- AI was repeating same platitudes ("the map is not the territory" 3x)
- No humor or playfulness
- Ignoring user pushback
- Generic self-help advice

### Solution: watts-rag.ts
Created input categorization system with 8 categories:
- existential, pushback, complaint, fear, frustration, meta, greeting, general

Each category has:
- Pattern matching rules
- Response examples with pondering + response
- Techniques for that input type
- Anti-patterns to avoid

### Key Features
1. **Anti-repetition**: Tracks phrases used in conversation, injects "DO NOT REPEAT" list
2. **Pushback handling**: Special reminder for humor + agreement when user challenges
3. **Meta awareness**: Self-aware humor when user calls out repetition
4. **Dynamic examples**: Randomly selects 2 examples per request to avoid staleness

### Results (Study Loop v2)
Before → After:
- Overall: 85.6 → **95.0/100**
- Challenge rate: 1/6 → **5/6** (target >4) ✅
- Humor rate: 1/11 → **6/11** (target >5) ✅
- Engagement: 6/11 → **8/11** (target >7) ✅
- Repetition: variable → **100/100** ✅
- Self-help patterns: some → **0/11** ✅

### Files Changed
- Created: src/config/watts-rag.ts (mini-RAG system)
- Updated: src/config/prompts.ts (integrated RAG context)
- Updated: src/app/api/chat/route.ts (passes input for categorization)
- Updated: scripts/study-loop.ts (expanded challenge detection)

## [bug] 2026-01-25 17:00 - Forge SDK hang - Artemis auth header mismatch

## Problem
Forge using Claude Agent SDK was hanging after receiving the initial SystemMessage from the Claude Code CLI subprocess.

## Root Cause Analysis
1. **Claude Code CLI subprocess starts correctly** - We receive the `init` SystemMessage
2. **Query is sent** - SDK sends query to CLI via stdin
3. **CLI tries to make API call** - CLI calls Artemis proxy at ANTHROPIC_BASE_URL
4. **Auth header mismatch** - Claude Code CLI uses `x-api-key` header (Anthropic SDK standard), but Artemis only accepted `Authorization: Bearer` header
5. **API call fails silently** - CLI hangs waiting for response

## Fixes Applied
1. **Artemis proxy_routes.py** - Updated `validate_api_key()` to accept both:
   - `Authorization: Bearer art_xxx` (original)
   - `x-api-key: art_xxx` (Anthropic SDK compatibility)

2. **Artemis /v1/messages endpoint** - Already existed, routes Claude SDK requests through OpenRouter

3. **Forge config.py** - Updated `get_sdk_env()` to:
   - Include full `os.environ` (so CLI has PATH, etc.)
   - Set proper `ANTHROPIC_API_KEY` (not placeholder)
   - Add CI/headless mode env vars

## Remaining Issue
The Artemis API key in Forge's Railway env (`art_xMMLtLksavmqNy9iZaoDDMHybSKicsrLelEGOdeGVh4`) returns "Invalid or revoked API key". Need to create a new valid key via artemis-cli.

## Key Learning
When using Claude Agent SDK with a proxy:
- The SDK spawns Claude Code CLI as subprocess
- CLI uses standard Anthropic SDK internally
- Anthropic SDK uses `x-api-key` header, not `Authorization: Bearer`
- Proxy must accept both header formats for compatibility

## [learning] 2026-01-25 17:06 - Forge-Artemis Architecture - HARD REQUIREMENT

## HARD REQUIREMENT: Forge → Artemis → LLM Provider

**All Forge requests MUST route through Artemis. This is non-negotiable.**

### Why Artemis?
- **Token counting** - Artemis tracks all input/output tokens
- **Usage logging** - Per-request logging with cost calculation
- **Cost analytics** - Dashboard for monitoring spend
- **Rate limiting** - Centralized control
- **Multi-provider routing** - Can route to Anthropic, OpenRouter, OpenAI, etc.

### Architecture
```
Forge (Claude Agent SDK)
    ↓
    ANTHROPIC_BASE_URL=https://artemis.jettaintelligence.com
    ↓
Artemis (LLM Proxy)
    ↓
    Routes to configured provider (OpenRouter, Anthropic direct, etc.)
    ↓
LLM Provider (Anthropic API)
```

### Configuration
Forge environment variables:
- `ARTEMIS_URL=https://artemis.jettaintelligence.com`
- `ARTEMIS_API_KEY=art_xxx` (Artemis API key for the Forge service account)

The Claude Agent SDK uses these via `get_sdk_env()`:
- `ANTHROPIC_BASE_URL` → points to Artemis
- `ANTHROPIC_API_KEY` → Artemis API key (Artemis authenticates, then uses its own provider keys)

### Provider Keys in Artemis
The Forge service account group needs provider keys configured in Artemis:
- OpenRouter key (for routing Claude models via OpenRouter)
- OR Anthropic key directly (for direct Anthropic API access)

Either works - Artemis handles the routing. The key point is ALL traffic goes through Artemis for tracking.

### Never Bypass Artemis
- Never set ANTHROPIC_BASE_URL to api.anthropic.com directly
- Never use Anthropic API keys in Forge directly
- All LLM calls must be proxied through Artemis

## [feature] 2026-01-25 17:09 - Forge SDK Integration - WORKING

## Forge Claude Agent SDK Integration - RESOLVED

Successfully got Forge working with Claude Agent SDK routing through Artemis.

### Final Working Architecture
```
Forge (Claude Agent SDK)
    ↓ ANTHROPIC_BASE_URL=https://artemis.jettaintelligence.com
    ↓ ANTHROPIC_API_KEY=art_xxx (Forge service account key)
Artemis (LLM Proxy)
    ↓ Authenticates via x-api-key header
    ↓ Routes to /v1/messages endpoint
    ↓ Tracks tokens, calculates cost
OpenRouter
    ↓
Anthropic Claude API
```

### Test Result
```json
{
  "type": "task_completed",
  "summary": "4",
  "cost_usd": 0.01357088,
  "duration_ms": 1287,
  "artifacts": []
}
```

### Fixes Required
1. **Artemis auth header** - Added `x-api-key` header support (Claude SDK uses this, not `Authorization: Bearer`)
2. **Forge service account** - Created via `artemis-cli admin create-account forge`
3. **OpenRouter provider key** - Added to Forge group via `artemis-cli admin add-provider openrouter --account forge`
4. **Railway env update** - Updated `ARTEMIS_API_KEY` with new valid key

### Key Files Modified
- `artemis/app/routers/proxy_routes.py` - Added x-api-key header support in `validate_api_key()`
- `forge/forge/config.py` - Include full `os.environ` in SDK env, proper API key passthrough

### Commands Used
```bash
# Create Forge service account
python scripts/artemis-cli.py admin create-account forge --description "Forge autonomous agent service"

# Issue API key (save this!)
# Output: art_WJjpGp3aFtewC2tTSZ6JPjVYdwt91zmgeokJbdJ46CI

# Add OpenRouter provider key to Forge group
python scripts/artemis-cli.py admin add-provider openrouter --key "$OPENROUTER_KEY" --account forge

# Update Railway env
mcp__Railway__set-variables ARTEMIS_API_KEY=art_xxx
```

### Token Counting Verified
Artemis successfully tracks:
- Input/output tokens
- Cost calculation ($0.0136 for simple query)
- Request logging
- Usage analytics

## [feature] 2026-01-26 01:48 - RheaOS Desktop: AI Remote Control API

## Summary
Built comprehensive API for AI-driven control of RheaOS Electron app. Enables full automation of Claude Code sessions.

## API Endpoints (port 7420)

### Core
- `GET /health` - App status
- `GET /state` - Full app state
- `GET /logs` - Action logs

### Sessions
- `POST /sessions` - Create session
- `POST /sessions/:id/input` - Send input (auto-focuses)
- `GET /sessions/:id/output` - Read terminal buffer
- `DELETE /sessions/:id` - Kill session

### DevTools Protocol
- `GET /devtools/dom?selector=X` - Query DOM
- `POST /devtools/eval` - Execute JS in renderer
- `GET /devtools/styles?selector=X` - CSS inspection
- `GET /devtools/elements` - List visible elements

### Visual
- `GET /screenshot` - Capture window PNG

## Key Bug Fix: Enter Key Not Working

**Problem:** `\r` was being sent but not submitting input to Claude Code.

**Root Cause:** Window needed focus for terminal input to process.

**Fix:** Auto-focus window before sending input in API handler:
```javascript
if (mainWindow && !mainWindow.isDestroyed()) {
  mainWindow.focus();
}
session.pty.write(data);
```

**Technical Details:**
- Enter = carriage return = `\r` = `0x0d`
- JSON `\r` correctly parses to byte `0x0d`
- Electron PTY requires window focus

## Key Bug Fix: PTY Spawn Failed

**Problem:** `posix_spawnp failed` error when creating sessions.

**Root Cause:** node-pty native module not built for Electron.

**Fix:** Rebuild native modules:
```bash
npx electron-rebuild -f -w node-pty
```

## Architecture
- Main process: HTTP server, session management, PTY processes, DevTools Protocol
- Renderer process: xterm.js terminals, UI state
- IPC: session:created event syncs API-created sessions to renderer
- Logging: All actions to ~/.rheaos/actions.log

## Files
- `/Users/dshanklinbv/repos-personal/rhea-os/desktop/src/main.js` - Main process with API
- `/Users/dshanklinbv/repos-personal/rhea-os/desktop/API.md` - Full API documentation

## [schema] 2026-01-26 22:07 - Artemis Data Model Redesign - Teams & Services (Phase 1)

# Artemis Data Model Redesign - Phase 1 Complete

## Problem Statement
The existing Artemis data model had several issues:
- "Group" was overloaded: held users AND API keys AND provider accounts
- Service accounts were Users with `is_service_account=True` (not first-class entities)
- No team association for services
- Hard to slice analytics by team vs service vs key creator
- Historical analytics would break when relationships changed

## Solution: Separate Teams from Services

### New Tables Created

**teams** - Groups of people within an organization
```sql
- id, organization_id, name, description
- status (active/archived)
- created_by_user_id, created_at, deleted_at (soft delete)
- UNIQUE(organization_id, name)
```

**team_members** - Pivot table for users in multiple teams
```sql
- id, team_id, user_id
- role (admin/member)
- added_at, added_by_user_id
- UNIQUE(team_id, user_id)
```

**services** - Applications that call LLMs (forge, taskr, watts, etc.)
```sql
- id, organization_id, team_id (owning team)
- name, description
- status (active/suspended), suspended_at, suspended_reason, suspended_by_user_id
- alert_threshold_cents (rolling 24h spend alert)
- monthly_budget_cents (optional hard/soft cap)
- created_by_user_id, created_at, deleted_at (soft delete)
- UNIQUE(organization_id, name)
```

### Modified Tables

**api_keys** - New columns:
- `service_id` - FK to services table
- `environment` - prod/staging/dev
- `expires_at` - Key expiration timestamp
- `rotation_group_id` - Links keys from same rotation cycle

**usage_logs** - Denormalized snapshots (NO foreign keys for historical stability):
- `service_id` - Service that made the request
- `team_id_at_request` - Team owning service at request time
- `api_key_created_by_user_id` - Who created the API key

## Key Design Decisions

1. **Denormalized snapshots on usage_logs**: These capture state AT REQUEST TIME and don't change if relationships change later. This ensures historical analytics remain accurate even if a service moves to a different team.

2. **Soft deletes everywhere**: `deleted_at` column on teams and services for audit trail and recovery.

3. **Service suspension**: Instant revocation capability via `status='suspended'` - will be enforced in proxy.

4. **Environment dimension**: API keys can be tagged as prod/staging/dev for filtering.

## Migration Strategy
- Phase 1: ✅ Add new tables (no breaking changes)
- Phase 2: Seed data (create Platform Team, Service records)
- Phase 3: Dual write (usage logging captures snapshots)
- Phase 4: Dashboard cutover (analytics using new model)
- Phase 5: Cleanup (deprecate is_service_account)

## Files Changed
- `app/models.py` - Added Team, TeamMember, Service models; modified APIKey, UsageLog
- `app/routers/health.py` - Manual migration endpoint for Railway
- `alembic/versions/f6g7h8i9j0k1_add_teams_and_services.py` - Migration file

## Deployment
- Committed and pushed to main
- Railway auto-deployed
- Migration endpoint executed successfully
- All tables and columns verified

## Testing Status
- Health endpoint: ✅
- Admin API: ✅ (5 users found)
- LLM Proxy routing: ✅ (402 from OpenRouter = working, just needs credits)
- Database schema: ✅ (all tables/columns exist)
- App startup: ✅ (no schema errors)

## [feature] 2026-01-26 22:13 - Artemis Phase 1 Integration Tests - All Passed

# Artemis Phase 1 Integration Tests - PASSED

## Test Results Summary

| Test | Status | Details |
|------|--------|---------|
| Schema Check | ✅ | All tables and columns exist |
| Create Team | ✅ | "Platform Team" created in forge Service org |
| Add Team Member | ✅ | daniel@boone.voyage added as admin |
| Create Service | ✅ | "forge-test" with alert threshold |
| Issue Service Key | ✅ | API key with environment=dev |
| API Key Works | ✅ | 402 from OpenRouter (credits) = Artemis working |
| Suspend Service | ✅ | Status changed, timestamp recorded |
| Reactivate Service | ✅ | Status restored to active |
| Get Team Details | ✅ | Shows members and services |
| Soft Delete | ✅ | Records retained with deleted_at set |

## Schema Verification (All True)

```json
{
  "table_teams": true,
  "table_team_members": true,
  "table_services": true,
  "api_keys_service_id": true,
  "api_keys_environment": true,
  "api_keys_expires_at": true,
  "api_keys_rotation_group_id": true,
  "usage_logs_service_id": true,
  "usage_logs_team_id_at_request": true,
  "usage_logs_api_key_created_by_user_id": true,
  "all_schema_checks_passed": true
}
```

## New Admin API Endpoints (Tested)

### Teams
- `GET /api/v1/admin/organizations` - List all orgs
- `POST /api/v1/admin/teams` - Create team
- `GET /api/v1/admin/teams` - List teams
- `GET /api/v1/admin/teams/{id}` - Get team with members/services
- `POST /api/v1/admin/teams/{id}/members` - Add member
- `DELETE /api/v1/admin/teams/{id}` - Soft delete

### Services
- `POST /api/v1/admin/services` - Create service
- `GET /api/v1/admin/services` - List services
- `GET /api/v1/admin/services/{id}` - Get with API keys
- `POST /api/v1/admin/services/{id}/keys` - Issue key
- `POST /api/v1/admin/services/{id}/suspend` - Suspend
- `POST /api/v1/admin/services/{id}/activate` - Reactivate
- `DELETE /api/v1/admin/services/{id}` - Soft delete

### Utility
- `GET /api/v1/admin/schema-check` - Verify migration

## Test Data Created/Cleaned

1. **Platform Team** - Created, member added, then soft deleted
2. **forge-test Service** - Created with $50 alert threshold, key issued, suspended, reactivated, then soft deleted
3. **API Key** - art_PUpafizg... (dev environment) - successfully authenticated

## Key Findings

1. **API Key Authentication**: New service-linked keys work correctly
2. **Soft Delete**: Works as expected - records stay in DB with deleted_at timestamp
3. **Team → Service relationship**: Services show up in team details
4. **Environment dimension**: API keys can be tagged (dev/staging/prod)
5. **Service suspension**: Status tracking works but proxy enforcement not yet implemented (Phase 3)

## Next Steps (Phase 2-5)

- Phase 2: Seed real data (migrate existing service accounts to Services)
- Phase 3: Dual write (usage_logs snapshots team_id_at_request)
- Phase 4: Dashboard cutover
- Phase 5: Cleanup deprecated fields

## [general] 2026-01-26 22:32 - Artemis Data Model Migration - TRIAGE & GAP ANALYSIS

# Artemis Data Model Migration - TRIAGE

## Current State Summary

### Old Model (Still in Use)
| Service Account | Org | Keys | Last Used |
|----------------|-----|------|-----------|
| forge | forge Service | 2 | 2026-01-27 |
| taskr | taskr Service | 2 | 2026-01-26 |
| watts | watts Service | 1 | 2026-01-26 |
| test-cli | test-cli Service | 2 | never |

### New Model (Empty)
- Teams: 1 (soft deleted test)
- Services: 1 (soft deleted test)
- Schema: ✅ All tables/columns exist

### Provider Keys
- Only 1 OpenRouter key configured (in Default group)
- **BLOCKER**: OpenRouter account has insufficient credits (402 errors)

---

## Gap Analysis

### GAP 1: Service Suspension Not Enforced in Proxy
**File**: `app/routers/proxy_routes.py`
**Issue**: Service suspension status is tracked but NOT checked during API key validation
**Impact**: Suspended services can still make API calls
**Fix Required**: Add check in `validate_api_key()` to reject requests if `api_key.service.status == 'suspended'`

### GAP 2: Usage Logs Don't Capture New Fields
**File**: `app/routers/proxy_routes.py`
**Issue**: `service_id`, `team_id_at_request`, `api_key_created_by_user_id` are NOT populated
**Impact**: New analytics slicing won't work until this is fixed
**Fix Required**: Update `log_usage()` to capture these denormalized snapshots

### GAP 3: Dashboard Doesn't Use New Model
**File**: `app/routers/analytics.py`
**Issue**: Dashboard still uses Group-based queries, no Service/Team slicing
**Impact**: Can't slice by service or team in UI
**Fix Required**: Add dropdowns and queries for service_id, team_id filters

### GAP 4: Existing Service Accounts Not Migrated
**Issue**: forge, taskr, watts, test-cli exist as Users with `is_service_account=True`, not as Service records
**Impact**: New model is empty, can't use new features
**Fix Required**: Create Service records and link existing API keys

### GAP 5: OpenRouter Credits Depleted
**Issue**: All proxy tests return 402 "Insufficient credits"
**Impact**: Can't verify LLM proxy functionality
**Fix Required**: Add credits to OpenRouter account or add alternative provider key

### GAP 6: Only One Provider Key
**Issue**: Single OpenRouter key, no fallback providers
**Impact**: Single point of failure, no cost optimization options
**Recommendation**: Add Anthropic direct key as fallback

---

## Migration Blockers

### Blocker 1: Old Keys Have No service_id
Existing API keys were created before `service_id` column existed.
**Decision Needed**:
- Option A: Create Services that match old Organizations, link keys
- Option B: Create new keys for Services, deprecate old keys
- Option C: Backfill service_id on existing keys

### Blocker 2: Org-per-Service vs Shared Org
Current model: Each service account has its OWN organization
New model design: Services belong to a SHARED organization (AIC Holdings)

**Decision Needed**:
- Keep separate orgs per service? (current)
- Consolidate into single AIC Holdings org? (planned)
- Support both models?

### Blocker 3: Provider Key Scope
Current: Provider keys belong to Groups (which belong to Orgs)
New model: Provider keys should be org-wide (shared across Services)

**Decision Needed**: How to handle provider key ownership during migration?

---

## Recommended Migration Path

### Phase 2A: Create AIC Holdings Org + Platform Team
```
1. Create "AIC Holdings" organization (or use existing)
2. Create "Platform Team" within that org
3. Add daniel@boone.voyage to Platform Team as admin
```

### Phase 2B: Create Service Records
```
1. Create Service "forge" in AIC Holdings, owned by Platform Team
2. Create Service "taskr" in AIC Holdings, owned by Platform Team
3. Create Service "watts" in AIC Holdings, owned by Platform Team
4. Create Service "test-cli" in AIC Holdings, owned by Platform Team
```

### Phase 2C: Link Existing Keys (Option A)
```
1. UPDATE api_keys SET service_id = '<forge-service-id>' WHERE user_id = '<forge-user-id>'
2. Repeat for taskr, watts, test-cli
```

### Phase 3: Enable Dual Write
```
1. Update proxy_routes.py to populate usage_logs snapshot fields
2. Update validate_api_key() to check service suspension
```

### Phase 4: Dashboard Update
```
1. Add Service dropdown to dashboard filters
2. Add Team dropdown to dashboard filters
3. Add GROUP BY queries for new dimensions
```

---

## Open Questions

1. **Should we consolidate orgs?**
   - Current: 4 separate orgs (forge Service, taskr Service, etc.)
   - Proposed: 1 shared org (AIC Holdings)
   - Pro: Simpler, matches intended design
   - Con: Breaking change, need to migrate provider keys

2. **What about test-cli?**
   - Never used (last_used=never)
   - Keep or delete?

3. **Provider key credits?**
   - OpenRouter is empty
   - Add credits or switch providers?

4. **Backfill historical usage_logs?**
   - Should we UPDATE old usage_logs with service_id based on api_key_id?
   - Or leave historical data as-is?

---

## Immediate Actions Needed

1. ⚠️ **Add OpenRouter credits** - Blocking all LLM testing
2. 📋 **Decide on org consolidation** - Affects migration approach
3. 🔧 **Implement service suspension check** - Security gap
4. 📊 **Create Services for existing accounts** - Enable new model

## [schema] 2026-01-26 22:32 - Artemis Proxy - Service Suspension Enforcement Design

# Artemis: Service Suspension Enforcement Design

## Current State
The `validate_api_key()` function in `proxy_routes.py` only checks:
1. API key exists (by hash)
2. Key is not revoked (`revoked_at IS NULL`)

It does NOT check the service status.

## Required Change

### Location: `app/routers/proxy_routes.py`

### Current validate_api_key() Flow:
```python
async def validate_api_key(request: Request, db: AsyncSession):
    # 1. Extract key from header (Authorization or x-api-key)
    # 2. Hash the key
    # 3. Look up in api_keys table
    # 4. Check revoked_at is NULL
    # 5. Return api_key, user_id
```

### Required Addition:
```python
async def validate_api_key(request: Request, db: AsyncSession):
    # ... existing validation ...

    # NEW: Check if key's service is suspended
    if api_key.service_id:
        result = await db.execute(
            select(Service).where(Service.id == api_key.service_id)
        )
        service = result.scalar_one_or_none()
        if service and service.status == "suspended":
            raise HTTPException(
                status_code=403,
                detail=f"Service '{service.name}' is suspended: {service.suspended_reason or 'No reason provided'}"
            )

    return api_key, user_id
```

## Error Response Format
```json
{
  "error": {
    "code": "SERVICE_SUSPENDED",
    "message": "Service 'forge' is suspended: Budget exceeded",
    "type": "policy",
    "category": "policy",
    "recovery": {
      "action": "contact_admin",
      "message": "Contact your administrator to reactivate the service"
    }
  }
}
```

## Edge Cases

### 1. Keys Without service_id
- Old keys created before migration
- Should STILL WORK (no service = no suspension check)
- Graceful degradation

### 2. Soft-Deleted Services
- Check `deleted_at IS NULL` as well
- Soft-deleted services should NOT block keys
- Or should they? (Decision needed)

### 3. Performance
- Extra DB query per request (JOIN or separate)
- Consider eager loading service with api_key
- Or cache service status

## Implementation Priority
**HIGH** - This is a security/control gap. Admins expect suspension to immediately block access.

## Testing
1. Create service, issue key, verify works
2. Suspend service, verify key returns 403
3. Reactivate service, verify key works again
4. Test key without service_id still works

## [schema] 2026-01-26 22:33 - Artemis Usage Logging - Denormalized Snapshots Design

# Artemis: Usage Logging Denormalized Snapshots

## Why Denormalized?

When a service moves from Team A to Team B, historical usage should STAY attributed to Team A (where it was at request time). This is why we snapshot rather than rely on JOINs.

## New Fields in usage_logs

| Field | Source | Purpose |
|-------|--------|---------|
| `service_id` | `api_key.service_id` | Slice by service |
| `team_id_at_request` | `api_key.service.team_id` | Slice by team (snapshot) |
| `api_key_created_by_user_id` | `api_key.user_id` | Slice by key creator |

## Current log_usage() Location

`app/routers/proxy_routes.py` around line 700-800

```python
async def log_usage(
    db: AsyncSession,
    api_key: APIKey,
    provider: str,
    model: str,
    usage_data: dict,
    ...
):
    usage_log = UsageLog(
        api_key_id=api_key.id,
        provider=provider,
        model=model,
        input_tokens=usage_data.get("prompt_tokens", 0),
        output_tokens=usage_data.get("completion_tokens", 0),
        # ... other fields ...
    )
```

## Required Addition

```python
async def log_usage(...):
    # Capture denormalized snapshots
    service_id = api_key.service_id  # May be None for old keys
    team_id_at_request = None

    if service_id:
        # Get team_id from service (at request time)
        result = await db.execute(
            select(Service.team_id).where(Service.id == service_id)
        )
        team_id_at_request = result.scalar_one_or_none()

    usage_log = UsageLog(
        api_key_id=api_key.id,
        provider=provider,
        model=model,
        # ... existing fields ...

        # NEW: Denormalized snapshots
        service_id=service_id,
        team_id_at_request=team_id_at_request,
        api_key_created_by_user_id=api_key.user_id,
    )
```

## Performance Consideration

Extra query to get team_id from service. Options:

### Option A: Separate Query (Simple)
- Extra SELECT per request
- ~1ms overhead
- Acceptable for now

### Option B: Eager Load in validate_api_key()
- JOIN api_key → service in initial validation
- Pass service to log_usage()
- Better performance

### Option C: Cache Service→Team Mapping
- Redis or in-memory cache
- Refresh on team/service changes
- Overkill for current scale

**Recommendation**: Start with Option A, optimize later if needed.

## Backfill Consideration

**Question**: Should we backfill historical usage_logs?

**Pro**:
- Full analytics from day 1
- Consistent data

**Con**:
- Need to map old api_key_id → service_id (which doesn't exist yet)
- Historical data may not be accurate if services didn't exist

**Recommendation**: Don't backfill. New fields will be populated going forward. Historical data remains as-is (nulls for new fields).

## Dashboard Query Examples

### By Service (last 30 days)
```sql
SELECT service_id, SUM(input_tokens + output_tokens) as total_tokens
FROM usage_logs
WHERE created_at > NOW() - INTERVAL '30 days'
  AND service_id IS NOT NULL
GROUP BY service_id
```

### By Team
```sql
SELECT team_id_at_request, COUNT(*) as request_count
FROM usage_logs
WHERE created_at > NOW() - INTERVAL '30 days'
  AND team_id_at_request IS NOT NULL
GROUP BY team_id_at_request
```

### By Key Creator
```sql
SELECT api_key_created_by_user_id, SUM(cost_cents) as total_cost
FROM usage_logs
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY api_key_created_by_user_id
```

## [general] 2026-01-26 22:33 - Artemis Triage - GitHub Issues & Session Context

# Artemis Triage - Session Started

## Taskr Session
- **ID**: 0b98d91f-4e09-4ff7-b182-688e6710ec54
- **Started**: 2026-01-27T04:33:35

## Handoff Notes from Previous Session
> OpenRouter meetrhea-artemis-01 key at $13.98/$20 monthly - caused 402 error. User clarified these are personal keys not for work. Consider setting up work-specific OpenRouter key with higher limits. Remaining artemis issues: #18, #19.

## GitHub Issues (aic-holdings/artemis)

### Open Issues (2)
| # | Title | Priority | Age |
|---|-------|----------|-----|
| 13 | Test embeddings endpoint locally with OpenRouter | testing | 9 days |
| 9 | [Optional] Data migration from Coolify PostgreSQL | low | 10 days |

**Note**: Neither issue relates to Teams & Services work. Need to create issues.

### Missing Issues (Work Not Tracked)
1. **Artemis Data Model - Phase 2: Seed Data** - Create Services for forge/taskr/watts
2. **Artemis Data Model - Phase 3: Dual Write** - Usage log snapshots
3. **Artemis Data Model - Phase 4: Dashboard** - New analytics dimensions
4. **Artemis Data Model - Phase 5: Cleanup** - Deprecate is_service_account
5. **Service Suspension Enforcement** - Proxy should check service.status
6. **OpenRouter Credits Depleted** - Need work-specific API key

## Recent Devlogs (from session)
1. aic-docs Railway deployment with Jetta SSO
2. Project Paused: watts-demo
3. Forge persistent logging + Artemis key cleanup
4. OpenRouter weekly credit limit exhausted - Forge blocked
5. Lesson: Never deploy agentic systems with ephemeral logs
6. Added artemis breakdown command for usage analytics
7. Added persistent task logging to Forge
8. Fixed Artemis token tracking for streaming requests

## Key Context from Last Session
- Fixed Forge persistent logging (forge schema with forge_tasks/forge_task_events)
- Artemis token tracking now works
- Closed artemis #17 (CLI refactor)
- OpenRouter 402 blocks Forge until credit reset

## Recommended Actions
1. Create GitHub issues for Phase 2-5 work
2. Prioritize service suspension enforcement (security gap)
3. Set up work-specific OpenRouter key (or alternative provider)
4. Phase 2 can proceed without LLM testing (database operations only)

## [general] 2026-01-26 22:34 - Artemis Triage Complete - 3 Issues Created

# Artemis Triage Complete

## Issues Created

| # | Title | Priority | Type |
|---|-------|----------|------|
| [#20](https://github.com/aic-holdings/artemis/issues/20) | Data Model: Phase 2 - Seed Services | medium | enhancement |
| [#21](https://github.com/aic-holdings/artemis/issues/21) | Data Model: Phase 3 - Dual Write Usage Logs | medium | enhancement |
| [#22](https://github.com/aic-holdings/artemis/issues/22) | Security: Enforce service suspension in proxy | **HIGH** | security |

## Total Open Issues: 5
- #9 - Data migration (low priority, optional)
- #13 - Test embeddings locally
- #20 - Phase 2 seed data
- #21 - Phase 3 dual write
- #22 - Service suspension enforcement

## Recommended Priority Order

1. **#22 - Service Suspension** (security gap)
   - Can implement now
   - No dependencies
   - Critical for production safety

2. **#20 - Phase 2 Seed Data**
   - Creates Services, links keys
   - Required before Phase 3
   - Can do without LLM testing

3. **#21 - Phase 3 Dual Write**
   - Depends on #20
   - Enables analytics slicing

4. **Phase 4/5** (not yet tracked)
   - Dashboard updates
   - Cleanup deprecated fields

## Blockers

### OpenRouter Credits
- 402 errors on all LLM requests
- Handoff note: "personal keys not for work"
- **Action needed**: Set up work-specific OpenRouter key
- Workaround: Phase 2/3 work is DB-only, doesn't need LLM

## Session
- **ID**: 0b98d91f-4e09-4ff7-b182-688e6710ec54
- **Status**: Active
- **Next action**: Implement #22 (service suspension)

## [feature] 2026-01-26 22:44 - Artemis #22 Complete - Service Suspension Enforcement

# Artemis #22 - Service Suspension Enforcement

## Summary
Implemented service suspension enforcement in the proxy. Suspended services now immediately block API access.

## Change
**File**: `app/routers/proxy_routes.py`

Added to `validate_api_key()` function:
```python
# Check if key's service is suspended
if api_key.service_id:
    service_result = await db.execute(
        select(Service).where(Service.id == api_key.service_id)
    )
    service = service_result.scalar_one_or_none()
    if service and service.status == "suspended":
        reason = service.suspended_reason or "Contact administrator"
        raise HTTPException(
            status_code=403,
            detail=f"Service '{service.name}' is suspended: {reason}"
        )
```

## Test Results

| Step | Expected | Actual | ✓ |
|------|----------|--------|---|
| Create service | Created | bb168970... | ✅ |
| Issue key | Key issued | art_WCP16B7D... | ✅ |
| Test key (active) | 402 (OpenRouter) | 402 | ✅ |
| Suspend service | Suspended | Suspended | ✅ |
| Test key (suspended) | 403 | `"Service 'suspension-test' is suspended: Testing suspension enforcement"` | ✅ |
| Reactivate service | Activated | Activated | ✅ |
| Test key (active again) | 402 (OpenRouter) | 402 | ✅ |
| Cleanup | Deleted | Deleted | ✅ |

## Error Response Format
```json
{
  "detail": "Service 'suspension-test' is suspended: Testing suspension enforcement"
}
```

## Edge Cases Handled
1. **Keys without service_id**: Pass through unchanged (graceful degradation)
2. **Service not found**: No error (key still works)
3. **Active services**: Pass through

## Commit
`d372bb9` - Security: Enforce service suspension in proxy (#22)

## GitHub Issue
Closes #22

## [feature] 2026-01-27 11:27 - Meridian QA: AI Jobs page deployed

## Fix: AI Processing Jobs monitoring now live

### Problem
- `/ai-jobs` page returning 404 after commit
- Railway hadn't picked up the new deployment automatically

### Solution
- Ran `railway up --detach` to trigger manual redeploy
- Deployment completed successfully

### Verification
- Health endpoint: 200 OK
- `/ai-jobs`: 302 redirect to SSO (expected for auth routes)
- Route is live at https://qa.meridian.jettaintelligence.com/ai-jobs

### GitHub
- Closed issue aic-holdings/meridian-qa#6

### Features Now Live
- KPIs: success rate, stuck count, completed/failed (7d)
- Stuck jobs alert (>30min in processing)
- Performance by capture type with avg processing time
- Recent jobs table with processing time vs waiting time
- AI Jobs link in nav bar (orange highlight)

## [feature] 2026-01-27 11:57 - Meridian QA: Incident tracking deployed

## Incident Tracking System Live

### What Was Built
- `qa_incidents` table with computed `time_to_resolve_minutes` column
- 8 new database functions for incident CRUD
- Auto-create incidents when alerts fire
- Auto-resolve when conditions clear
- /incidents dashboard with KPIs
- Manual acknowledge/resolve buttons

### Files Changed
- database.py: +180 lines (incident functions + alert integration)
- main.py: +60 lines (routes and API endpoints)
- templates/incidents.html: new (dashboard template)
- templates/base.html: +1 line (nav link)

### KPIs Enabled
- Avg time to resolve (30d)
- Open incident count
- Resolution rate by incident type
- Breakdown showing which incident types take longest

### Verification
- Table created in Supabase with all 15 columns
- App loads successfully with 3 new routes
- Page displays correctly at qa.meridian.jettaintelligence.com/incidents
- Auto-resolution tested via check_for_alerts() logic

## [feature] 2026-01-27 12:09 - Taskr Worker: Meridian QA monitor job deployed

## Meridian QA Monitor Job

### What Was Added
- New Tier 0 job in taskr-worker: `meridian_qa`
- Polls qa.meridian.jettaintelligence.com/api/v1/alerts/check every 5 min
- Creates/resolves incidents in qa_incidents table
- Sends Telegram for critical alerts

### Files
- worker/jobs/meridian_qa.py (new)
- worker/config.py (added MERIDIAN_QA_INTERVAL)
- worker/main.py (registered as Tier 0 job)
- worker/jobs/__init__.py (export)

### Config
- MERIDIAN_QA_INTERVAL=300 (5 min default)
- MERIDIAN_QA_URL (defaults to production)
- TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (optional)

### Deployment
- PR #4 merged to main
- Railway auto-deploys from main branch

## [bugfix] 2026-01-27 12:23 - Meridian QA incident tracking - bugs fixed, API key needed

## Summary

Fixed bugs in taskr-worker's meridian_qa job. Created GitHub issues for tracking.

## Issues Created
- taskr-worker#5: Wrong HTTP method + missing auth (FIXED in commit 3759b9a)
- meridian-qa#7: Create API key for taskr-worker

## Code Fix (Committed)
- Changed from `POST /api/v1/alerts/check` to `GET /api/v1/alerts`
- Added `X-API-Key` header support
- Added `MERIDIAN_QA_API_KEY` env var support
- Gracefully skips if API key not configured

## Manual Steps Needed (Railway)

### 1. Meridian-QA Railway
Add to environment variables:
```
API_KEYS=sk_501448151956fd4895f7d2ab54b0634a
```
(Or append to existing API_KEYS with comma separator)

### 2. Taskr-Worker Railway
Add to environment variables:
```
MERIDIAN_QA_API_KEY=sk_501448151956fd4895f7d2ab54b0634a
```

### 3. Verify
- Check taskr-worker logs for `meridian_qa` job runs
- Should see `alerts_found` count in logs
- Visit qa.meridian.jettaintelligence.com/incidents to see any created incidents

## Session
- Started: 65d6212b-b999-4d0f-b949-0649b1a55608
- Used taskr_triage to guide workflow

## [feature] 2026-01-27 12:23 - Telegram Project Notifications

## taskr-worker Telegram Integration

### Configuration
- **Bot**: @taskr_aic_bot
- **Bot Token**: `8400174224:AAGsBn_OdZ7OqyvFfUedJRbjn5U7QWrrimg`
- **Group Chat ID**: `-1003738535950` (AIC Taskr supergroup)
- **Projects Topic ID**: `12` (message_thread_id for forum topic)

### Notification Types

1. **Job Alerts** (main group - no topic)
   - `notify_job_error(job_name, error, tier)` - Job failures
   - `notify_job_recovered(job_name, tier)` - When failed job starts working again
   - `notify_startup(job_count, tier_counts)` - Worker startup
   - `notify_shutdown()` - Worker shutdown

2. **Project Updates** (Projects topic - thread_id=12)
   - `notify_project_created(name, id)` - New project discovered
   - `notify_project_updated(name, id, changes)` - Project changes
   - `notify_project_sync(total, new, updated)` - After GitHub sync

### Implementation
- `worker/telegram.py` - All notification functions
- Uses `message_thread_id` parameter to send to specific forum topics
- Topic constant: `TOPIC_PROJECTS = 12`

### Railway Env Vars
- `TELEGRAM_BOT_TOKEN`: Bot API token
- `TELEGRAM_CHAT_ID`: `-1003738535950` (group chat)

### Future Topics
Can add more forum topics for different notification categories (e.g., Issues, Alerts, etc.)


## [feature] 2026-01-27 12:39 - taskr-worker Telegram + GitHub Sync Complete

## Session Summary

Completed full Telegram integration and GitHub project sync for taskr-worker.

### What Was Done

1. **Telegram Notifications**
   - Bot: @taskr_aic_bot
   - Group chat: AIC Taskr (`-1003738535950`)
   - Projects topic (thread_id=12) for project updates
   - Job error/recovery notifications to main group

2. **Database Schema**
   - Added `one_liner` and `categories` columns to `taskr.devlogs`
   - Created GitHub sync tables: `github_projects`, `github_project_items`, `github_issues`, `config`
   - Added `aic-holdings` as default sync org

3. **GitHub Sync**
   - Syncing 31 projects from aic-holdings
   - Project items and field values stored
   - Summary notifications to Projects topic (avoids rate limits)

4. **Bug Fixes**
   - Set `logging.basicConfig(level=logging.INFO)` for structlog visibility
   - JSON serialize `field_values` for JSONB columns
   - Removed per-project notifications to avoid Telegram rate limits

### Railway Config
- Project: `amusing-generosity`
- Service: `taskr-worker`
- New env vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GITHUB_TOKEN`

### Commits
- `a2c0eb9` - fix: Use structlog for Telegram logging
- `5fc5233` - feat: Add project notifications to Telegram Projects topic
- `c4fe33f` - fix: Set root logger to INFO level
- `a7391fb` - fix: JSON serialize field_values for JSONB column
- `107d9bb` - fix: Remove individual project notifications to avoid rate limits

### Closed Issues
- #3 Deploy worker to Railway - DONE

## [feature] 2026-01-27 12:48 - taskr-worker Telegram + GitHub Sync Complete

## Session Summary

Full Telegram integration and GitHub project sync for taskr-worker completed and tested.

### Features Implemented

**1. Telegram Notifications**
- Bot: @taskr_aic_bot (token: `8400174224:AAG...`)
- Group: AIC Taskr (`-1003738535950`)
- Projects topic (thread_id=12) for project updates
- Job error/recovery notifications to main group
- Rate limit handling (summary only, no per-project spam)

**2. GitHub Project Sync**
- 31 projects synced from aic-holdings
- 434 project items tracked
- Tables: `github_projects`, `github_project_items`, `github_issues`, `config`
- Summary notifications to Projects topic after sync

**3. Database Schema Updates**
- Added `one_liner` (VARCHAR 200) to devlogs
- Added `categories` (TEXT[]) to devlogs
- Migrated existing `category` values to array

### Bug Fixes
- `logging.basicConfig(level=logging.INFO)` - structlog INFO visibility
- `json.dumps(fields)` - JSONB serialization for field_values
- Removed per-project notifications to avoid Telegram 429 rate limits

### Current Stats
| Data | Count |
|------|-------|
| Devlogs | 425 (147 summarized) |
| Sessions | 494 (338 summarized) |
| GitHub Projects | 31 |
| Project Items | 434 |

### Railway Config
- Project: `amusing-generosity`
- Service: `taskr-worker`
- Env vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GITHUB_TOKEN`

### Files Modified
- `worker/telegram.py` - Notifications with topic support
- `worker/main.py` - Logging config
- `worker/jobs/github_sync.py` - Project sync with notifications
- `worker/jobs/summarize.py` - Uses new columns

### GitHub
- Closed: #3 Deploy worker to Railway
- Open: #2 Knowledge extraction (needs claude-agent-sdk)

### Telegram Topic IDs
```
AIC Taskr Group: -1003738535950
Projects Topic: message_thread_id=12
```

## [feature] 2026-01-31 17:21 - Migrated embeddings.py from SQLite to PostgreSQL + pgvector

## Summary
Rewrote `reeves/embeddings.py` (~900 lines) to use PostgreSQL with pgvector instead of SQLite.

## Key Changes

### Database Switch
- **Before**: SQLite with JSON-encoded embeddings, Python cosine similarity calculation
- **After**: PostgreSQL with pgvector Vector(1024) column, HNSW index for fast similarity search

### Functions Migrated
- `store_embedding()` → writes to `embeddings.knowledge_vectors` table
- `search()` → uses pgvector `<=>` operator with HNSW index
- `find_similar()` → native pgvector similarity
- `embed_all_*()` → query PostgreSQL via SQLAlchemy ORM
- `find_orphan_task_matches()` → ORM + pgvector
- `find_similar_projects()` → ORM + pgvector
- `find_unassigned_area_matches()` → ORM
- `validate_area_assignment()` → ORM + pgvector
- `create_area_mismatch_flag()` → ORM
- `resolve_area_mismatch_flag()` → ORM

### Technical Decisions
1. **Keep Ollama for embedding generation** - local, no API costs, works offline
2. **Use pgvector for storage/search** - HNSW index is 10-100x faster than Python loops
3. **Use CAST() instead of ::vector** - avoids SQLAlchemy parameter binding conflicts
4. **Added `_embedding_to_list()` helper** - handles numpy arrays and pgvector strings

### Gotchas Fixed
- pgvector returns embeddings as strings from raw SQL, need to parse with json.loads()
- numpy arrays serialize with `np.float32()` wrapper, need to convert to plain floats
- SQLAlchemy `::` cast syntax conflicts with named parameters, use `CAST()` instead

## Test Results
```
search() - OK (19 results for "AWS security")
find_similar() - OK (5 similar entities)
find_orphan_task_matches() - OK (15 matches)
find_similar_projects() - OK (0 pairs)
find_unassigned_area_matches() - OK (7 tasks, 0 projects)
validate_area_assignment() - OK
embed_all() - OK (processed 316 embeddings)
```

## Files Changed
- `reeves/embeddings.py` - Complete rewrite for PostgreSQL
- `reeves/embeddings_sqlite_backup.py` - Backup of old version

## Next Steps
1. Migrate `suggestions.py` to PostgreSQL
2. Migrate `task_priority.py` to PostgreSQL
3. Remove `init_db()` from web.py
4. Delete SQLite files after verification

## [learning] 2026-01-31 17:25 - PostgreSQL Embeddings Testing - Semantic Insights

## Summary
Comprehensive testing of the new PostgreSQL + pgvector embeddings system. Found interesting semantic insights and data quality issues.

## Embedding Stats
- **Total embeddings**: 322 (reeves schema)
- **Table size**: 4.5 MB
- **HNSW index size**: 2.5 MB (for fast similarity search)

### Coverage by entity type:
- task: 124
- completion: 64
- area: 39
- project: 24
- task_learning: 21
- task_note: 20
- log: 17
- artifact: 10
- skillflow: 3

## Semantic Insights

### Area Relationships (make sense!)
- Social & Relationships ↔ Family & Parenting: 70%
- Finance ↔ Legal & Compliance: 66%
- Health & Wellness ↔ Family & Parenting: 61%

### Area → Best Task Matches
- Daily Operations → Morning email triage (70%)
- Finance → 30-day spending trend analysis (58%)
- Home - The Bowery → Weekly Grocery Reorder (56%)

### Learning Transfer Potential
Learnings could help tasks they weren't created for:
- "COSTCO → Groceries" could help "Weekly Grocery Reorder" (64%)
- "Amazon SES email verification" could help "Morning Email Triage" (57%)
- "AMZN* → Shopping" could help "30-day spending trend analysis" (52%)

## Data Quality Issues Found

### Tasks with empty names: 9
Need cleanup - likely test data

### Duplicate task names:
- "Weekly Grocery Reorder" appears 3 times
- "[FEEDBACK] Fix bug: /tasks/{id}/start" appears 2 times

### Orphan task with 96% project match:
- Task "Complete Oura Ring 4 Purchase" should probably be in project "Oura Ring 4 Purchase"

## Performance
- Search: ~57ms (includes Ollama embedding generation)
- pgvector search alone: <10ms with HNSW index
- Re-index all: processed 316 entities successfully

## [general] 2026-02-01 22:58 - Perplexity Comet Session - Subscription Cleanup & Admin Tasks

## Work Completed via Perplexity Comet (Feb 1, 2026)

### Subscription Cancellations
- **VEED Pro** - Cancelled ($936/year, ends Feb 16, 2026)
- **TradingView Premium** - Cancelled ($67.95/month = $815/year, ends Feb 28, 2026)
- **Recall Plus** - Cancelled ($84/year, ends Feb 8, 2026)

### Settings/Notifications Disabled
- Turned off Google Calendar notifications
- Turned off Mercury "Receipt Required" emails
- Unsubscribed from Dagster University weekly emails

### Notes Created
- OpenAI Pro can die (consider cancelling)
- Build our own Recall alternative (need to export data before Feb 8)

### Mercury API Email Drafted
Ready to send to api@mercury.com - requesting token scopes/security info for API integration

### Total Annual Savings
~$1,835/year from subscription cancellations

---
Agent: perplexity-comet
Session type: Admin/cleanup tasks

## [general] 2026-02-01 23:00 - Perplexity Comet Session - Detailed Subscription Audit & Cleanup

## Perplexity Comet Session - Feb 1, 2026 (Detailed)

### Subscription Cancellations

**1. VEED Pro - CANCELLED**
- Cost: $936/year
- Renewal date: Feb 16, 2026
- Reason: Not using video editing features enough to justify cost
- Action taken: Cancelled via account settings
- Access continues until: Feb 16, 2026

**2. TradingView Premium - CANCELLED**
- Cost: $67.95/month ($815.40/year)
- Renewal date: Feb 28, 2026
- Reason: Can use free tier for basic charting needs
- Action taken: Cancelled subscription
- Access continues until: Feb 28, 2026

**3. Recall Plus - CANCELLED**
- Cost: $84/year
- Renewal date: Feb 8, 2026
- Reason: Building our own alternative; Recall's data export is needed before cancellation takes effect
- Action taken: Cancelled subscription
- **URGENT**: Export all Recall data before Feb 8, 2026
- Follow-up task: Build own Recall-like memory/search tool

### Notification & Email Cleanup

**4. Google Calendar Notifications - DISABLED**
- What: Turned off push notifications for calendar events
- Why: Too many interruptions, prefer to check calendar manually

**5. Mercury "Receipt Required" Emails - DISABLED**
- What: Turned off automated emails asking for receipt uploads
- Why: Noise reduction; will handle receipts in batch

**6. Dagster University - UNSUBSCRIBED**
- What: Unsubscribed from weekly Dagster educational emails
- Why: Not actively using Dagster, inbox cleanup

### Notes for Future Action

**7. OpenAI Pro Subscription**
- Status: Still active, but questioning value
- Note: "OpenAI Pro can die" - consider cancelling
- Decision needed: Evaluate usage vs cost before next renewal

**8. Build Own Recall Alternative**
- Context: With Recall Plus cancelled, need our own solution
- Requirements: Memory capture, semantic search, timeline view
- Deadline: Have something basic before Feb 8 when Recall access ends
- Data export: Must export all Recall data before cancellation

### Mercury API Integration (Email Drafted)

**9. Email to Mercury API Team**
- Recipient: api@mercury.com
- Purpose: Request information about:
  - Available API token scopes
  - Security best practices for token storage
  - Rate limits and usage guidelines
  - Webhook capabilities for transaction notifications
- Status: Draft ready, needs to be sent
- Context: Setting up financial data sync for Reeves

---

### Summary
- **Subscriptions cancelled**: 3
- **Annual savings**: $1,835.40
- **Emails/notifications disabled**: 3
- **Pending decisions**: 1 (OpenAI Pro)
- **Urgent follow-up**: Export Recall data by Feb 8

### Agent Details
- Agent: Perplexity Comet
- Session type: Financial audit, subscription cleanup, admin tasks
- Duration: ~45 minutes

## [feature] 2026-02-03 20:19 - Webb-Tosh Integration: Family Discovery

## Summary
Expanded Webb relationship memory by syncing contacts from Tosh and discovering family relationships from message content.

## New Contacts Synced (8)
- Angie Shanklin, Beth Shanklin, Bryson Shanklin, Cheryl Shanklin
- Bryan Wilson, David Wilson, Heather Wilson, Larry Wilson

## Key Constraint Learned
**Not every Wilson is related just because of last name.** Only create relationship edges based on actual evidence from messages or explicit confirmation.

## Family Structure Discovered from Messages

### Daniel's Parents
- Joanne Traversaro (mother) - confirmed via "Mom" in messages
- John Traversaro (father, 80% confidence)

### Daniel's Siblings
- Steven Shanklin (brother, 70% confidence) - tech discussions, close relationship
- Michael Shanklin (brother) - married to Cheryl

### Daniel's Children
- Wyatt
- Colleen (daughter, distinct from grandma)

### Daniel's Ex-Spouse
- Taylor Wilson

### Nieces/Nephews (Michael's kids)
- Aiden Shanklin
- Bryson Shanklin

### Grandma
- Colleen Shanklin (passed away) - daughter Colleen's great-grandma

## Data Cleanup
- Fixed duplicate Colleen records (daughter vs grandma are different people)
- Deleted incorrect Steven PARENT_OF Daniel edge
- Deleted incorrect Michael CHILD_OF Steven edge
- Added proper sibling relationships

## Current Webb Stats
- 20 persons
- 77 relationship edges
- 23 phone contacts, 24 email contacts
- 9 CHILD_OF, 5 SIBLING_OF, 4 MARRIED_TO relationships

## [feature] 2026-02-03 20:47 - Webb Friend Discovery from Messages

## Summary
Searched Tosh messages to find friends (non-family relationships) and added them to Webb.

## Friends Discovered

### Brandon Johnson
- **Contact:** +1 817-297-8860, ebrandonj@gmail.com
- **Evidence:** Personal messages about Sanjay's birthday cookies, asking about Lucas's party, checking in about someone in hospital
- **Closeness:** friend
- **Added FRIEND_OF edge**

### Colin Christian
- **Contact:** +1 817-924-4152, christianclan@gmail.com
- **Evidence:** Very candid personal discussions - politics, relationships, recovery topics, college bills, bitcoin
- **Closeness:** friend (close friend based on candor)
- **Added FRIEND_OF edge**

### Jake Smith (already existed)
- Already marked as FRIEND_OF from prior data

## Tosh Limitation Found
**Bug:** `search_messages` only matches first OR last name, not full names.
- ❌ `search_messages(contact="Brandon Johnson")` → "No contact found"
- ✅ `search_messages(contact="Brandon")` → Returns messages

**Workaround:** Always search by first name only.

## Contacts Checked (No Personal Messages)
- Paul Johnson/Christensen - mostly automated Walmart/verification messages
- David Smith - no messages found
- Mike Fabiano - no messages found

## Current Webb Stats
- 22 persons (added Brandon, Colin)
- 3 FRIEND_OF relationships (Jake, Brandon, Colin)
- Friends now properly distinguished from family
