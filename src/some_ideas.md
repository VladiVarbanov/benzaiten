startup.py  

    ├── calls qwen_server.start_qwen_server()
    ├── initializes SQLite
    ├── checks workspace directories
    └── verifies required services

vllm_server.py -->        shared vLLM subprocess mechanics

qwen_server.py  -->        concrete Qwen launch profile

gemma_server.py  -->       concrete Gemma launch profile

startup.py    -->          starts the selected services

Agreed first version

Validate configuration
→ build explicit vLLM command
→ start Qwen
→ expose logs
→ wait for endpoint readiness
→ remain in foreground
→ stop cleanly