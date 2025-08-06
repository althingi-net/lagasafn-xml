# Legal Document Processing System - Architecture Design

## Executive Summary

This document outlines the proposed hexagonal architecture for a legal document processing system that handles multiple document types (laws, bills, adverts, changes) with support for various input formats (XML, HTML) and AI-powered parsing capabilities.

## Current State vs. Proposed Architecture

### Current Issues

- Mixed concerns in API endpoints (file access, parsing, business logic)
- No clear separation between data access and business rules
- Difficult to extend for new document types or parsing strategies
- Limited testability due to tight coupling

### Proposed Solution

Hexagonal Architecture with clear separation of:

- **Domain Layer**: Pure business logic and entities
- **Application Layer**: Use cases and orchestration
- **Infrastructure Layer**: External systems (files, AI services, parsers)

## Domain Model

### Core Entities

```bash
Law
├── identifier: string
├── name: string  
├── chapters: number
├── articles: number
├── status: LawStatus
└── content: LawContent

Bill  
├── identifier: string
├── name: string
├── law_changes: List<LawChange>
└── status: BillStatus

LawChange
├── target_law: LawIdentifier
├── change_type: ChangeType
└── modifications: List<Modification>

Document (Base)
├── identifier: string
├── name: string
├── document_type: DocumentType
└── metadata: DocumentMetadata
```

### Document Types

- **Laws**: Individual legal statutes
- **Bills**: Collections of proposed law changes
- **Adverts**: Legal announcements
- **Changes**: Modification records

## Architecture Layers

### 1. Domain Layer (`/domain/`)

Pure business logic with no external dependencies.

```bash
domain/
├── entities/
│   ├── law.py                    # Core Law entity
│   ├── bill.py                   # Bill as collection of law changes  
│   ├── document.py               # Base document entity
│   ├── law_change.py             # Individual law modification
│   └── validation_result.py      # Validation domain model
├── repositories/
│   ├── law_repository.py         # Abstract law data access
│   ├── bill_repository.py        # Abstract bill data access
│   └── document_repository.py    # Abstract document access
├── services/
│   ├── law_validator.py          # Business validation rules
│   └── bill_analyzer.py          # Bill impact analysis
└── value_objects/
    ├── law_identifier.py         # Strong typing for identifiers
    └── document_metadata.py      # Metadata value object
```

### 2. Application Layer (`/application/`)

Use cases and orchestration logic.

```bash
application/
├── use_cases/
│   ├── list_laws_use_case.py         # Current /xml-files logic
│   ├── get_law_document_use_case.py  # Retrieve single law
│   ├── get_bill_document_use_case.py # Retrieve bill details
│   ├── validate_law_use_case.py      # Law validation workflow
│   ├── analyze_bill_impact_use_case.py # Bill impact analysis
│   └── search_documents_use_case.py  # Document search
├── dto/
│   ├── law_list_dto.py               # API response models
│   ├── law_detail_dto.py             # Detailed law response
│   └── validation_report_dto.py      # Validation results
└── ports/
    ├── parsing_service.py            # Abstract parsing interface
    └── ai_service.py                 # Abstract AI service interface
```

### 3. Infrastructure Layer (`/infrastructure/`)

External system integrations and technical implementations.

```bash
infrastructure/
├── repositories/
│   ├── xml_law_repository.py         # XML file system access
│   ├── xml_bill_repository.py        # Bill XML processing
│   ├── xml_document_repository.py    # Generic XML documents
│   └── composite_document_repository.py # Multi-source aggregation
├── parsers/
│   ├── xml_parser.py                 # Pure XML parsing utilities
│   ├── html_to_xml_parser.py         # HTML conversion
│   ├── law_xml_parser.py             # Law-specific XML logic
│   ├── bill_xml_parser.py            # Bill-specific XML logic
│   └── advert_xml_parser.py          # Advertisement parsing
├── ai/
│   ├── ai_law_parser.py              # AI-powered parsing
│   ├── ai_validation_service.py      # AI validation assistance
│   └── ai_client.py                  # AI service client
└── validation/
    ├── xml_schema_validator.py       # Technical XML validation
    ├── data_integrity_validator.py   # Data consistency checks
    └── business_rule_validator.py    # Business logic validation
```

## API Layer Integration

```python
# Example: Refactored endpoint
@api.get("/xml-files")
def list_xml_files(request: HttpRequest) -> List[LawListDto]:
    use_case = ListLawsUseCase(
        law_repository=get_law_repository(),
        document_parser=get_xml_parser()
    )
    return use_case.execute()
```

## Benefits of This Architecture

### 1. **Separation of Concerns**

- Domain logic is isolated from technical details
- Easy to understand and maintain each layer
- Clear boundaries between different responsibilities

### 2. **Testability**

- Domain logic can be tested without file system
- Infrastructure can be mocked for fast unit tests
- Integration tests can focus on specific components

### 3. **Extensibility**

- New document types: Add new entities and parsers
- New input formats: Implement new repository adapters
- New AI services: Swap implementations via interfaces

### 4. **Maintainability**

- Changes in one layer don't affect others
- Easy to locate and fix issues
- Clear code organization
