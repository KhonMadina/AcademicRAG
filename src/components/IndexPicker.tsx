import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { chatAPI, type IndexSummary } from '@/lib/api';
import { Loader2, MailOpen, MoreVertical, Trash2 } from 'lucide-react';
import Swal from 'sweetalert2';
import toast from 'react-hot-toast';

interface Props {
  onSelect: (indexId: string) => void;
  onClose: () => void;
}

type PickerIndex = IndexSummary & {
  id: string;
  name: string;
};

export default function IndexPicker({ onSelect, onClose }: Props) {
  const [indexes, setIndexes] = useState<PickerIndex[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [deletingIndexId, setDeletingIndexId] = useState<string | null>(null);
  const isMountedRef = useRef(true);

  const loadIndexes = useCallback(async (showFeedback = false) => {
    const toastId = showFeedback ? toast.loading('Refreshing indexes...') : undefined;
    try {
      if (isMountedRef.current) {
        setLoading(true);
        setError(null);
      }
      const data = await chatAPI.listIndexes();
      if (!isMountedRef.current) return;

      const nextIndexes = (Array.isArray(data.indexes) ? data.indexes : [])
        .map((index) => {
          const id = typeof index.id === 'string'
            ? index.id
            : typeof index.index_id === 'string'
              ? index.index_id
              : null;

          const name = typeof index.name === 'string' && index.name.trim().length > 0
            ? index.name
            : typeof index.title === 'string' && index.title.trim().length > 0
              ? index.title
              : id;

          if (!id || !name) return null;
          return { ...index, id, name } as PickerIndex;
        })
        .filter((index): index is PickerIndex => index !== null);
      setIndexes(nextIndexes);
      if (toastId) {
        toast.success('Indexes refreshed.', { id: toastId });
      }
    } catch (e: unknown) {
      if (!isMountedRef.current) return;
      const message = e instanceof Error ? e.message : 'Failed to load indexes';
      setError(message);
      if (toastId) {
        toast.error(message, { id: toastId });
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    loadIndexes();
  }, [loadIndexes]);

  const filteredIndexes = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    if (!normalizedSearch) return indexes;

    return indexes.filter((index) => index.name.toLowerCase().includes(normalizedSearch));
  }, [indexes, search]);

  const handleDelete = useCallback(async (idxId: string, name: string) => {
    if (deletingIndexId) return;

    const confirmDelete = await Swal.fire({
      title: 'Delete index?',
      text: `Delete index "${name}"? This cannot be undone.`,
      icon: 'warning',
      showCancelButton: true,
      confirmButtonText: 'Delete',
      cancelButtonText: 'Cancel',
      confirmButtonColor: '#991b1b',
      cancelButtonColor: '#374151',
    });

    if (!confirmDelete.isConfirmed) return;

    setDeletingIndexId(idxId);
    const toastId = toast.loading('Deleting index...');
    try {
      await chatAPI.deleteIndex(idxId);
      setIndexes((prev) => prev.filter((index) => index.id !== idxId));
      setMenuOpenId(null);
      toast.success('Index deleted.', { id: toastId });
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Failed to delete index';
      toast.error(message, { id: toastId });
      await Swal.fire({
        title: 'Delete failed',
        text: message,
        icon: 'error',
        confirmButtonColor: '#991b1b',
      });
    } finally {
      setDeletingIndexId(null);
    }
  }, [deletingIndexId]);

  useEffect(() => {
    function handleOutside(event: MouseEvent) {
      const target = event.target as Element;
      if (!target.closest('[data-index-menu-root="true"]')) {
        setMenuOpenId(null);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setMenuOpenId(null);
      }
    }

    if (menuOpenId) {
      document.addEventListener('mousedown', handleOutside);
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('mousedown', handleOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [menuOpenId]);

  return (
    <div className="fixed inset-0 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white/80 backdrop-blur rounded-xl w-full max-w-xl max-h-full overflow-y-auto p-6 space-y-6 border border-black/20 shadow-2xl">
        <h2 className="text-lg font-semibold">Select an index</h2>
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search indexes"
          className="w-full px-3 py-2 rounded bg-white/50 border border-black/50 text-black/80 hover:cursor-text"
        />
        {loading && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Loader2 className="w-4 h-4 animate-spin" />
            <p>Loading</p>
          </div>
        )}
        {error && (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-red-400/60 bg-red-500/10 px-3 py-2">
            <p className="text-sm text-red-500">{error}</p>
            <button
              onClick={() => loadIndexes(true)}
              disabled={loading}
              className="px-3 py-1 rounded bg-red-800/80 hover:bg-red-800 text-white text-xs hover:cursor-pointer"
            >
              Retry
            </button>
          </div>
        )}
        {!loading && !error && (
          <ul className="space-y-2">
            {filteredIndexes.map((idx) => (
              <li key={idx.id}>
                <div className="relative group" data-index-menu-root="true">
                  <button
                    onClick={() => onSelect(idx.id)}
                    className="w-full px-4 py-3 bg-black/15 hover:bg-black/20 rounded transition flex justify-between items-center pr-10 hover:cursor-pointer"
                  >
                    <span className="font-medium truncate max-w-[60%]">{idx.name}</span>
                    <span className="text-xs">{idx.documents?.length || 0} files</span>
                  </button>

                  <button
                    onClick={(event) => {
                      event.stopPropagation();
                      setMenuOpenId(menuOpenId === idx.id ? null : idx.id);
                    }}
                    title="More actions"
                    className="absolute right-4 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100  hover:cursor-pointer transition text-lg leading-none font-bold"
                  >
                    <MoreVertical className="w-4 h-4" />
                  </button>

                  {menuOpenId === idx.id && (
                    <div className="index-row-menu absolute right-0 top-full mt-2 bg-white backdrop-blur-lg border border-black/10 shadow-lg py-1 w-32 text-sm z-50 rounded-2xl p-2">
                      <button
                        onClick={() => {
                          onSelect(idx.id);
                          setMenuOpenId(null);
                        }}
                        className="flex items-center w-full text-left px-4 py-2 hover:bg-black/10 hover:cursor-pointer hover:rounded-2xl"
                      >
                        <MailOpen className="w-4 h-4 mr-2" />
                        <span>Open</span>
                      </button>
                      <button
                        onClick={() => handleDelete(idx.id, idx.name)}
                        disabled={deletingIndexId === idx.id}
                        className="flex items-center w-full text-left px-4 py-2 hover:bg-black/10 text-red-400 hover:text-red-500 hover:cursor-pointer hover:rounded-2xl disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <Trash2 className="w-4 h-4 mr-2" />
                        <span>{deletingIndexId === idx.id ? 'Deleting...' : 'Delete'}</span>
                      </button>
                    </div>
                  )}
                </div>
              </li>
            ))}
            {filteredIndexes.length === 0 && (
              <p className="text-sm text-gray-400">
                {indexes.length === 0 ? 'No indexes available.' : 'No indexes found.'}
              </p>
            )}
          </ul>
        )}
        <div className="pt-4 border-t border-white/10 flex justify-end">
          <button onClick={onClose} className="px-4 py-2 bg-red-800/80 rounded hover:bg-red-800 text-white text-sm">Close</button>
        </div>
      </div>
    </div>
  );
} 