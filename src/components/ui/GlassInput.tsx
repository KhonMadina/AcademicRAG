"use client";
import React, { InputHTMLAttributes } from 'react';

export function GlassInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full rounded bg-white hover:bg-white/90 border border-black/30 focus:bg-white px-2 py-1 text-sm font-sans  outline-none focus:ring-2 focus:ring-black/20 transition hover:cursor-text ${props.className || ''}`}
    />
  );
} 