import { useEffect, useState } from 'react';
import { chatAPI } from '@/lib/api';
import { MoreVertical } from 'lucide-react';

interface Props {
  onSelect: (indexId: string) => void;
  onClose: () => void;
}

export default function IndexPicker({ onSelect, onClose }: Props) {
  const [indexes, setIndexes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await chatAPI.listIndexes();
        setIndexes(data.indexes);
      } catch (e: any) {
        setError(e.message || 'Failed to load indexes');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const filtered = indexes.filter(i => i.name.toLowerCase().includes(search.toLowerCase()));

  async function handleDelete(idxId: string, name: string) {
    if (!confirm(`Delete index "${name}"? This cannot be undone.`)) return;
    try {
      await chatAPI.deleteIndex(idxId);
      setIndexes(prev => prev.filter(i => i.id!==idxId));
      setMenuOpenId(null);
    } catch (e:any){
      alert(e.message || 'Failed to delete index');
    }
  }

  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if ((e.target as Element).closest('.index-row-menu') === null) {
        setMenuOpenId(null);
      }
    }
    if (menuOpenId) {
      document.addEventListener('click', handleOutside);
    }
    return () => document.removeEventListener('click', handleOutside);
  }, [menuOpenId]);

  return (
    <div className="fixed inset-0  backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white/80 backdrop-blur rounded-xl w-full max-w-xl max-h-full overflow-y-auto p-6 space-y-6 border border-black/20 shadow-2xl">
        <h2 className="text-lg font-semibold">Select an index</h2>
        <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search" className="w-full px-3 py-2 rounded bg-white/50 border border-black/50 text-black/80 hover:cursor-text" />
        {loading && <p className="text-sm text-gray-500">Loading</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}
        {!loading && !error && (
          <ul className="space-y-2">
            {filtered.map(idx => (
              <li key={idx.id}>
                <div className="relative group">
                  <button onClick={()=>onSelect(idx.id)} className="w-full px-4 py-3 bg-black/15 hover:bg-black/20 rounded transition flex justify-between items-center pr-10 hover:cursor-pointer">
                    <span className="font-medium truncate max-w-[60%]">{idx.name}</span>
                    <span className="text-xs">{idx.documents?.length || 0} files</span>
                  </button>

                  <button onClick={(e)=>{e.stopPropagation(); setMenuOpenId(menuOpenId===idx.id?null:idx.id);}} title="More actions" className="absolute right-4 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100  hover:cursor-pointer transition text-lg leading-none font-bold">
                   <MoreVertical className="w-4 h-4" />
                  </button>

                  {menuOpenId===idx.id && (
                    <div className="index-row-menu absolute right-0 top-full mt-2 bg-white backdrop-blur border border-black/10 shadow-lg py-1 w-32 text-sm z-50 rounded-2xl p-2">
                      <button onClick={()=>{onSelect(idx.id); setMenuOpenId(null);}} className="block w-full text-left px-4 py-2 hover:bg-black/10 hover:cursor-pointer hover:rounded-2xl">Open</button>
                      <button onClick={()=>handleDelete(idx.id, idx.name)} className="block w-full text-left px-4 py-2 hover:bg-black/10 text-red-400 hover:text-red-500 hover:cursor-pointer hover:rounded-2xl">Delete</button>
                    </div>
                  )}
                </div>
              </li>
            ))}
            {filtered.length===0 && <p className="text-sm text-gray-400">No indexes found.</p>}
          </ul>
        )}
        <div className="pt-4 border-t border-white/10 flex justify-end">
          <button onClick={onClose} className="px-4 py-2 bg-red-800/80 rounded hover:bg-red-800 text-white text-sm">Close</button>
        </div>
      </div>
    </div>
  );
} 