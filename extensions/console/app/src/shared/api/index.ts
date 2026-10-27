// The one way the client reaches the server (ARCHITECTURE.md §1): a typed GET of an /api route.
import { $fetch } from '#imports'

export function getJson<T>(path: `/api/${string}`): Promise<T> {
  return $fetch<T>(path)
}
