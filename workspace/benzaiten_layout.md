benzaiten/
│
├── src/
│   ├── config.py
│   ├── run_orchestrator.py
│   ├── orchestrator.py
│   ├── document_preparation.py
│   ├── knowledge_extraction.py
│   └── knowledge_extraction_coordinator.py
│
├── prompts/
│   └── ...                                  # Model instructions and prompt fragments
│
├── templates/
│   ├── okf_draft_protocol_v0.json           # Structure of intermediate OKF Drafts
│   ├── okf_draft_protocol_vocabulary.yaml   # Vocabulary used by the draft protocol
│   ├── okf_template.md                      # Authoritative final OKF template
│   ├── okf_vocabulary.yaml                  # Vocabulary used by final OKFs
│   ├── orchestrator_communication_protocol_v0.json
│   ├── orchestrator_communication_protocol_vocabulary.yaml
│   ├── plan_protocol_v1.json
│   ├── plan_protocol_vocabulary.yaml
│   └── plan_protocol_notes.md
│
├── workspace/
│   │
│   ├── inbox/
│   │   └── ...                              # Newly submitted, not-yet-registered input
│   │
│   ├── tmp/
│   │   │                                    # Incomplete and unsafe-to-consume work
│   │   │
│   │   ├── document_preparation/
│   │   │   └── <source_id>/
│   │   │       └── <preparation_work_id>/
│   │   │           └── ...
│   │   │
│   │   └── knowledge_extraction/
│   │       └── <target_okf_id>/
│   │           └── <extraction_work_id>/
│   │               └── ...
│   │
│   └── artifacts/
│       │                                    # Completed, validated, non-authoritative products
│       │
│       ├── document_preparation/
│       │   └── <source_id>/
│       │       └── <preparation_work_id>/
│       │           ├── prepared.md
│       │           ├── images/
│       │           ├── tables/
│       │           ├── chunks/
│       │           ├── page_map.json
│       │           └── preparation_manifest.json
│       │
│       └── knowledge_extraction/
│           └── <target_okf_id>/
│               └── <extraction_work_id>/
│                   ├── responses/
│                   ├── drafts/
│                   ├── synthesis/
│                   └── extraction_manifest.json
│
└── vault/
    │                                        # Authoritative persistent knowledge
    │
    ├── sources/
    │   └── <source_id>/
    │       ├── source_manifest.json
    │       └── ...                          # PDF, webpage capture, note, idea, etc.
    │
    ├── OKF/
    │   └── <target_okf_id>.md               # One authoritative source-derived OKF
    │
    ├── projects/
    │   └── ...                              # Knowledge aggregated around projects
    │
    └── concepts/
        └── ...                              # Knowledge aggregated around concepts