---
type: concept
tags: []
compiled_at: "2026-09-01"
partition: work
---
# Order Service
## Overview
The shop's order service takes orders from the storefront and hands them to fulfilment.

## Storage
Orders live in Postgres 15 on the primary database host, with a read replica for reports.

## Queues
New orders go to the export queue; payment events go to [[Kafka]].

## Retries
A failed hand-off retries 5 times, one minute apart, before it pages the on-call engineer.

## Limits
The service accepts at most 200 orders a minute; the storefront shows a queue page above that.

## Owners
Blake Sample owns the service; Avery Sample owns the storefront side.

## History
The service replaced the old order script in 2025. Its first release had no retries.

## Runbook
Restart with the deploy tool; check the export queue depth first; never drop the queue.

## Metrics
Dashboards show orders a minute, hand-off failures, queue depth and replica lag.

## Open items
Moving reports off the replica is planned for next quarter.
## Overview
The shop's order service takes orders from the storefront and hands them to fulfilment.

## Storage
Orders live in Postgres 15 on the primary database host, with a read replica for reports.

## Queues
New orders go to the export queue; payment events go to [[Kafka]].

## Retries
A failed hand-off retries 5 times, one minute apart, before it pages the on-call engineer.

## Limits
The service accepts at most 200 orders a minute; the storefront shows a queue page above that.

## Owners
Blake Sample owns the service; Avery Sample owns the storefront side.

## History
The service replaced the old order script in 2025. Its first release had no retries.

## Runbook
Restart with the deploy tool; check the export queue depth first; never drop the queue.

## Metrics
Dashboards show orders a minute, hand-off failures, queue depth and replica lag.

## Open items
Moving reports off the replica is planned for next quarter.
## Overview
The shop's order service takes orders from the storefront and hands them to fulfilment.

## Storage
Orders live in Postgres 15 on the primary database host, with a read replica for reports.

## Queues
New orders go to the export queue; payment events go to [[Kafka]].

## Retries
A failed hand-off retries 5 times, one minute apart, before it pages the on-call engineer.

## Limits
The service accepts at most 200 orders a minute; the storefront shows a queue page above that.

## Owners
Blake Sample owns the service; Avery Sample owns the storefront side.

## History
The service replaced the old order script in 2025. Its first release had no retries.

## Runbook
Restart with the deploy tool; check the export queue depth first; never drop the queue.

## Metrics
Dashboards show orders a minute, hand-off failures, queue depth and replica lag.

## Open items
Moving reports off the replica is planned for next quarter.
