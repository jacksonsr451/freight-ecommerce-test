import { useQuery } from '@tanstack/react-query';
import { getHealth } from '../api/health';
import { getRuntime } from '../api/runtime';

export function useHealth() {
  return useQuery({ queryKey: ['local-health'], queryFn: ({ signal }) => getHealth(signal) });
}

export function useRuntime() {
  return useQuery({ queryKey: ['local-runtime'], queryFn: ({ signal }) => getRuntime(signal) });
}
