run_orchestrator.py
    receive raw request
    validate environment
    call communication parser
    call global orchestrator
    print generic response
    return exit code

orchestrator_communication.py
    load communication protocol
    parse envelope
    validate protocol contract
    normalize request

orchestrator.py
    verify action exists
    select capability coordinator
    dispatch request
    normalize capability result/error

document_preparation_coordinator.py
    coordinate document-preparation work

knowledge_extraction_coordinator.py
    coordinate parallel extraction and synthesis

document_preparation.py
    document-preparation domain operations

knowledge_extraction.py
    knowledge-extraction domain operations

model_client.py
    communicate with model endpoints