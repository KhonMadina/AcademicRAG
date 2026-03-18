"use client";
import React, { InputHTMLAttributes } from 'react';

export function GlassInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full px-2 py-2 bg-white hover:bg-white/90 border border-white-600 rounded-sm focus:bg-white  text-xs font-sans  outline-none focus:ring-2 focus:ring-black/20 transition hover:cursor-text ${props.className || ''}`}
    />
  );
} 