"use client";
import React from 'react';

interface Props {
  checked: boolean;
  onChange: (v: boolean) => void;
}

export function GlassToggle({ checked, onChange }: Props) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={`w-10 h-5 rounded-full transition hover:cursor-pointer relative ${checked ? 'bg-green-500/70' : 'bg-black/20'} font-sans`}
    >
      <span
        className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${checked ? 'translate-x-5' : ''}`}
      />
    </button>
  );
} 