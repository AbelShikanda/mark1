/// <reference types="vite/client" />
import axios, { AxiosInstance } from 'axios';

export const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});
