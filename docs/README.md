# Documentation Index

## Guides
- [Migration Guide](guides/MIGRATION_GUIDE.md) - Upgrading from obs-tools to obs-sync v2.x

## Architecture
- [SQLite Reader Architecture](architecture/sqlite-reader-architecture.md) - Implementation details for SQLite-based task reading
- [Deduplication Implementation](architecture/deduplication-implementation.md) - Task deduplication algorithm and approach
- [Tag Sync Implementation](architecture/tag-sync-implementation.md) - Tag-based task routing and synchronization

## Bug Fixes & Investigations
- [Tag Routing Query Fix](bugfixes/bugfix-tag-routing-query.md) - Fix for spurious task deletions on second sync
- [EventKit Identifier Mismatch](bugfixes/EVENTKIT_IDENTIFIER_MISMATCH.md) - Apple Reminders calendar ID resolution issues

## Contributing

When adding new documentation:
- **Guides**: User-facing documentation, tutorials, migration guides
- **Architecture**: Technical implementation details, design decisions
- **Bug Fixes**: Post-mortem analysis of significant bugs and their fixes

Keep documentation concise and focused. Link to code when appropriate.