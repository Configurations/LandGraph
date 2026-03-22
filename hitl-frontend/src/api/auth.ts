import { apiFetch } from './client';
import type {
  GoogleClientIdResponse,
  LoginResponse,
  RegisterResponse,
  UserResponse,
} from './types';

export function login(email: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export function register(email: string, culture: string): Promise<RegisterResponse> {
  return apiFetch<RegisterResponse>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, culture }),
    skipAuth: true,
  });
}

export function googleAuth(credential: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>('/api/auth/google', {
    method: 'POST',
    body: JSON.stringify({ credential }),
    skipAuth: true,
  });
}

export function resetPassword(
  email: string,
  oldPassword: string,
  newPassword: string,
): Promise<{ ok: boolean; message: string }> {
  return apiFetch<{ ok: boolean; message: string }>('/api/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({ email, old_password: oldPassword, new_password: newPassword }),
    skipAuth: true,
  });
}

export function getMe(): Promise<UserResponse> {
  return apiFetch<UserResponse>('/api/auth/me');
}

export function getGoogleClientId(): Promise<GoogleClientIdResponse> {
  return apiFetch<GoogleClientIdResponse>('/api/auth/google/client-id', { skipAuth: true });
}
