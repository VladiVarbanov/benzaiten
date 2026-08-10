# Benzaiten Directory Layout

``` text
benzaiten/
│
├── src/
│   ├── config.py
│   ├── run_orchestrator.py
│   ├── orchestrator.py
│   ├── orchestrator_communication.py
│   ├── orchestrator_communication_validator.py
│   ├── document_preparation.py
│   ├── document_preparation_coordinator.py
│   ├── knowledge_extraction.py
│   ├── knowledge_extraction_coordinator.py
│   └── ...
│
├── prompts/
│   ├── planning_system_prompt.md
│   ├── knowledge_extraction_system_prompt.md
│   └── ...
│
├── protocols/
│   ├── communication/
│   │   ├── orchestrator_communication_protocol_v0.json
│   │   └── orchestrator_communication_protocol_vocabulary.yaml
│   ├── planning/
│   │   ├── plan_protocol_v1.json
│   │   ├── plan_protocol_vocabulary.yaml
│   │   └── old/
│   │       └── plan_protocol_v0.json
│   └── knowledge/
│       ├── okf_draft_protocol_v0.json
│       └── okf_draft_protocol_vocabulary.yaml
│
├── templates/
│   ├── okf_template.md
│   └── okf_vocabulary.yaml
│
├── workspace/
│   ├── inbox/
│   │   └── ...
│   ├── tmp/
│   │   ├── document_preparation/
│   │   │   └── <source_id>/
│   │   │       └── <preparation_work_id>/
│   │   │           └── ...
│   │   └── knowledge_extraction/
│   │       └── <target_okf_id>/
│   │           └── <extraction_work_id>/
│   │               └── ...
│   └── artifacts/
│       ├── document_preparation/
│       │   └── <source_id>/
│       │       └── <preparation_work_id>/
│       │           ├── prepared.md
│       │           ├── images/
│       │           ├── tables/
│       │           ├── chunks/
│       │           ├── page_map.json
│       │           └── preparation_manifest.json
│       └── knowledge_extraction/
│           └── <target_okf_id>/
│               └── <extraction_work_id>/
│                   ├── responses/
│                   ├── drafts/
│                   ├── synthesis/
│                   └── extraction_manifest.json
│
└── vault/
    ├── sources/
    │   └── <source_id>/
    │       ├── source_manifest.json
    │       └── ...
    ├── OKF/
    │   └── <target_okf_id>.md
    ├── projects/
    │   └── ...
    └── concepts/
        └── ...
```
