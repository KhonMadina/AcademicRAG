"use client";
import { useState } from 'react';
import { GlassInput } from '@/components/ui/GlassInput';
import { GlassToggle } from '@/components/ui/GlassToggle';
import { AccordionGroup } from '@/components/ui/AccordionGroup';
import { ModelSelect } from '@/components/ModelSelect';
import { chatAPI, ChatSession } from '@/lib/api';
import { InfoTooltip } from '@/components/ui/InfoTooltip';

interface Props {
  onClose: () => void;
  onIndexed?: (session: ChatSession) => void;
}

export function IndexForm({ onClose, onIndexed }: Props) {
  const [files, setFiles] = useState<FileList | null>(null);
  const [indexName, setIndexName] = useState('');
  const [chunkSize, setChunkSize] = useState(512);
  const [chunkOverlap, setChunkOverlap] = useState(64);
  const [windowSize, setWindowSize] = useState(5);
  const [enableEnrich, setEnableEnrich] = useState(true);
  const [retrievalMode, setRetrievalMode] = useState<'hybrid' | 'vector' | 'fts'>('hybrid');
  const [embeddingModel, setEmbeddingModel] = useState<string>();
  const DEFAULT_LLM = 'gemma3:4b-cloud';
  const [enrichModel, setEnrichModel] = useState<string>(DEFAULT_LLM);
  const [overviewModel, setOverviewModel] = useState<string>(DEFAULT_LLM);
  const [batchSizeEmbed, setBatchSizeEmbed] = useState(64);
  const [batchSizeEnrich, setBatchSizeEnrich] = useState(64);
  const [loading, setLoading] = useState(false);
  const [enableLateChunk, setEnableLateChunk] = useState(false);
  const [enableDoclingChunk, setEnableDoclingChunk] = useState(true);

  const handleSubmit = async () => {
    if (!files) return;
    setLoading(true);
    try {
      // 1. create index record
      const { index_id } = await chatAPI.createIndex(indexName);

      // 2. upload files to index
      await chatAPI.uploadFilesToIndex(index_id, Array.from(files));

      // 3. build index (run pipeline) with ALL OPTIONS
      await chatAPI.buildIndex(index_id, { 
        latechunk: enableLateChunk, 
        doclingChunk: enableDoclingChunk,
        chunkSize: chunkSize,
        chunkOverlap: chunkOverlap,
        retrievalMode: retrievalMode==='fts' ? 'bm25' : retrievalMode,
        windowSize: windowSize,
        enableEnrich: enableEnrich,
        embeddingModel: embeddingModel,
        enrichModel: enrichModel,
        overviewModel: overviewModel,
        batchSizeEmbed: batchSizeEmbed,
        batchSizeEnrich: batchSizeEnrich
      });

      // 4. create chat session and link index
      const session = await chatAPI.createSession(indexName);
      await chatAPI.linkIndexToSession(session.id, index_id);

      // 5. callback
      if (onIndexed) onIndexed(session);
    } catch (e) {
      console.error('Indexing failed', e);
      setLoading(false);
      alert('Indexing failed. See console for details.');
    }
  };

  return (
    <div className="relative bg-white/80 rounded-xl p-6 w-full max-w-3xl max-h-full overflow-y-auto scroll-smooth space-y-6 border border-black/20 shadow-2xl">
      {/* Loading overlay */}
      {loading && (
        <div className="absolute inset-0 backdrop-blur-sm flex flex-col items-center justify-center rounded-xl z-20">
          <div className="w-10 h-10 border-4 border-black/30 border-t-transparent rounded-full animate-spin"></div>
          <p className="mt-4 text-sm">Indexing this may take a moment</p>
        </div>
      )}

      <h2 className="text-lg font-semibold">Create new index</h2>

      {/* Name of index */}
      <div>
        <label className="block text-xs uppercase tracking-wide  mb-2">Name of index</label>
        <GlassInput placeholder="My project docs" value={indexName} onChange={(e)=>setIndexName(e.target.value)} />
      </div>

      {/* Upload & defaults */}
      <div className="space-y-4">
        <div>
          <label htmlFor="file-upload" className="block text-xs uppercase tracking-wide  mb-1">Attached files (PDF,.md,txt)</label>
          <label
            htmlFor="file-upload"
            className="flex flex-col items-center justify-center w-full h-16 border border-dashed border-black/20 rounded cursor-pointer hover:border-black/40 transition"
            onDragOver={(e)=>e.preventDefault()}
            onDrop={(e)=>{
              e.preventDefault();
              if (e.dataTransfer.files) {
                const incoming = Array.from(e.dataTransfer.files);
                const current = files ? Array.from(files) : [];
                const combined = current.concat(incoming).slice(0, 4);
                const dt = new DataTransfer();
                combined.forEach(f => dt.items.add(f));
                setFiles(dt.files);
              }
            }}
          >
            <svg width="32" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1." strokeLinecap="round" strokeLinejoin="round" className="mb-2"><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/><polyline points="7 10 12 5 17 10"/><line x1="12" y1="5" x2="12" y2="16"/></svg>
            <span className="text-xs mb-2">Drag & Drop documents here or click to browse</span>
            <input
              id="file-upload"
              type="file"
              accept="application/pdf,.docx,.doc,.html,.htm,.md,.txt"
              multiple
              className="hidden"
              onChange={(e) => {
                if (e.target.files) {
                  const incoming = Array.from(e.target.files);
                  const current = files ? Array.from(files) : [];
                  const combined = current.concat(incoming).slice(0, 4);
                  const dt = new DataTransfer();
                  combined.forEach(f => dt.items.add(f));
                  setFiles(dt.files);
                }
              }}
              disabled={!!files && files.length >= 4}
            />
          </label>
          {files && (
            <div className="mt-1 text-xs">
              <p className="text-green-400">{files.length} file(s) selected</p>
              {files.length >= 4 && (
                <p className="text-red-500">Maximum 4 files allowed.</p>
              )}
              <ul className="mt-1 space-y-1">
                {Array.from(files).map((file, idx) => (
                  <li key={file.name + idx} className="flex items-center justify-between bg-black/5 rounded px-2 py-1">
                    <span className="truncate max-w-[70%]">{file.name}</span>
                    <button
                      type="button"
                      className="ml-2 px-2 py-1 text-xs bg-red-500/80 text-white rounded hover:bg-red-700"
                      onClick={() => {
                        const newFiles = Array.from(files).filter((_, i) => i !== idx);
                        if (newFiles.length === 0) setFiles(null);
                        else {
                          const dt = new DataTransfer();
                          newFiles.forEach(f => dt.items.add(f));
                          setFiles(dt.files);
                        }
                      }}
                    >Remove</button>
                  </li>
                ))}
              </ul>
            </div>
          )}
            </div>

        {/* Retrieval mode & Late-chunk toggle */}
        <div>
          <label className="flex items-center gap-1 text-xs uppercase tracking-wide  mb-2 border-t border-black/10 py-4">Retrieval mode <InfoTooltip text="Choose how chunks are found. Hybrid combines full-text search with vectors; FTS uses textual matching only; Vector relies purely on dense similarity." /></label>
          <div className="flex gap-3">
            {(['hybrid','vector','fts'] as const).map((m)=>(
              <button key={m} onClick={()=>setRetrievalMode(m)} className={`px-3 py-1 rounded text-xs font-sans hover:cursor-pointer border border-black/30 ${retrievalMode===m?'bg-green-700/90 text-white':'bg-white/10 hover:bg-white/20'}`}>{m==='fts' ? 'FTS' : m}</button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-4 mt-4">
            <div className="flex items-center gap-2">
              <span className="text-xs ">Late-chunk vectors <InfoTooltip text="Split chunks into sub-vectors to improve recall, then merge them back after retrieval." size={12} /></span>
              <GlassToggle checked={enableLateChunk} onChange={setEnableLateChunk} />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs ">High-recall chunking <InfoTooltip text="Advanced sentence-level packing with Docling features for maximum recall. Both modes use token-based sizing." size={12} /></span>
              <GlassToggle checked={enableDoclingChunk} onChange={setEnableDoclingChunk} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4 mt-4">
            <div>
              <label className="flex items-center gap-1 text-xs mb-1 ">Chunk size <InfoTooltip text="Maximum token length for each chunk. Both legacy and high-recall modes now use token-based sizing." size={12} /></label>
              <GlassInput type="number" value={chunkSize} onChange={(e) => setChunkSize(parseInt(e.target.value))} />
            </div>
            <div>
              <label className="flex items-center gap-1 text-xs mb-1 ">Chunk overlap <InfoTooltip text="Tokens reused between adjacent chunks to preserve context." size={12} /></label>
              <GlassInput
                type="number"
                value={chunkOverlap}
                onChange={(e) => setChunkOverlap(parseInt(e.target.value))}
              />
            </div>
          </div>

          {/* Embedding & Overview models */}
          <div className="grid grid-cols-2 gap-4 mt-4">
            <div>
              <label className="flex items-center gap-1 text-xs mb-1 ">Embedding model <InfoTooltip text="Model used to generate dense vectors stored in the index." size={12} /></label>
              <ModelSelect 
                value={embeddingModel} 
                onChange={setEmbeddingModel}
                type="embedding"
                placeholder="Select embedding model"
              />
            </div>
            <div>
              <label className="flex items-center gap-1 text-xs mb-1 ">Overview LLM <InfoTooltip text="LLM that writes the short overview paragraph per document." size={12} /></label>
              <ModelSelect 
                value={overviewModel}
                onChange={setOverviewModel}
                type="generation"
                placeholder="Select overview LLM"
              />
            </div>
          </div>
        </div>

        {/* Contextual retrieval section */}
        <AccordionGroup title={<><span>Contextual Retrieval</span> <InfoTooltip text="Adds neighbour chunks into each original chunk then enriches with LLM  improves semantic continuity but increases indexing latency." /></>}>
          <div className="flex items-center gap-3">
            <span className="text-xs ">Enable</span>
            <GlassToggle checked={enableEnrich} onChange={setEnableEnrich}/>
          </div>
          <div className="grid grid-cols-2 gap-4 mt-3">
            <div>
              <label className="flex items-center gap-1 text-xs mb-1 ">Context window <InfoTooltip text="Number of neighbour chunks included when enriching context." size={12} /></label>
              <GlassInput type="number" value={windowSize} onChange={(e)=>setWindowSize(parseInt(e.target.value))} />
            </div>
            <div>
              <label className="block text-xs mb-1 ">Retrieval LLM</label>
              <ModelSelect 
                value={enrichModel}
                onChange={setEnrichModel}
                type="generation"
                placeholder="Select retrieval LLM"
              />
            </div>
          </div>
        </AccordionGroup>
      </div>

      {/* Advanced */}
      <AccordionGroup title={<><span>Batch Size</span> <InfoTooltip text="Control the number of chunks processed per batch. Larger values speed up indexing but require more memory." /></>}>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="flex items-center gap-1 text-xs mb-1 ">Embedding batch size <InfoTooltip text="Chunks processed per batch when producing embeddings." size={12} /></label>
            <GlassInput
              type="number"
              value={batchSizeEmbed}
              onChange={(e) => setBatchSizeEmbed(parseInt(e.target.value))}
            />
          </div>
          <div>
            <label className="flex items-center gap-1 text-xs mb-1 ">Context retrieval batch size <InfoTooltip text="Chunks sent per request during contextual enrichment." size={12} /></label>
            <GlassInput
              type="number"
              value={batchSizeEnrich}
              onChange={(e) => setBatchSizeEnrich(parseInt(e.target.value))}
            />
          </div>
        </div>
      </AccordionGroup>

      <div className="flex justify-end gap-3 pt-4 border-t border-black/10">
        <button  disabled={loading} onClick={onClose} className="px-4 py-2 bg-red-800/80 rounded hover:bg-red-800 text-sm hover:cursor-pointer text-white">
          Cancel
        </button>
        <button
          disabled={loading || !files || !indexName.trim()}
          onClick={handleSubmit}
          className="px-4 py-2 bg-green-700/90 rounded disabled:opacity-40 text-sm hover:cursor-pointer text-white"
        >
          {loading ? 'Indexing' : 'Start indexing'}
        </button>
      </div>
    </div>
  );
}                        