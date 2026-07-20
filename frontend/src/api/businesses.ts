// Endpoint function for business registration (M5.2). Reuses the shared
// apiClient so error handling / base URL stay in one place.

import type { BusinessRegistration, RegisteredBusiness } from '../types/api';
import { apiClient } from './client';

/** Drop empty/undefined optional fields so the backend sees them as absent. */
function compact(payload: BusinessRegistration): BusinessRegistration {
  const entries = Object.entries(payload).filter(
    ([, value]) => value != null && value !== '',
  );
  return Object.fromEntries(entries) as unknown as BusinessRegistration;
}

/** POST /api/businesses — register a new business, making it searchable. */
export function registerBusiness(
  payload: BusinessRegistration,
): Promise<RegisteredBusiness> {
  return apiClient.request<RegisteredBusiness>('/api/businesses', {
    method: 'POST',
    body: JSON.stringify(compact(payload)),
  });
}
