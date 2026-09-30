---
type: dashboard
---
# Dashboard (Dataview)

## Sources
```dataview
TABLE title, year, venue, file.mtime AS updated
FROM "wiki/sources"
SORT year DESC
```

## Recently updated concepts & entities
```dataview
TABLE type, updated
FROM "wiki/concepts" OR "wiki/entities"
SORT updated DESC
LIMIT 20
```

## Concepts by number of sources
```dataview
TABLE length(sources) AS n_sources
FROM "wiki/concepts"
SORT length(sources) DESC
```
