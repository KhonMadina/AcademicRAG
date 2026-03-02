"use client";

import { useState, useEffect } from "react"
import { RAGChat } from "@/components/ui/localgpt-chat"
import { SessionSidebar } from "@/components/ui/session-sidebar"
import { SessionChat } from '@/components/ui/session-chat'
import { chatAPI, ChatSession } from "@/lib/api"
import { LandingMenu } from "@/components/LandingMenu";
import { IndexForm } from "@/components/IndexForm";
import SessionIndexInfo from "@/components/SessionIndexInfo";
import IndexPicker from "@/components/IndexPicker";
import { QuickChat } from '@/components/ui/quick-chat'
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

export function Main() {
    const [currentSessionId, setCurrentSessionId] = useState<string | undefined>()
    const [currentSession, setCurrentSession] = useState<ChatSession | null>(null)
    const [showConversation, setShowConversation] = useState(false)
    const [backendStatus, setBackendStatus] = useState<'checking' | 'connected' | 'error'>('checking')
    const [sidebarRef, setSidebarRef] = useState<{ refreshSessions: () => Promise<void> } | null>(null)
    const [homeMode, setHomeMode] = useState<'HOME' | 'INDEX' | 'CHAT_EXISTING' | 'QUICK_CHAT'>('HOME')
    const [showIndexInfo, setShowIndexInfo] = useState(false)
    const [showIndexPicker, setShowIndexPicker] = useState(false)
    const [sidebarOpen, setSidebarOpen] = useState(true)

    console.log('Main component rendering...')

    useEffect(() => {
        console.log('Main component mounted')
        checkBackendHealth()
    }, [])

    const checkBackendHealth = async () => {
        try {
            const health = await chatAPI.checkHealth()
            setBackendStatus('connected')
            console.log('Backend connected:', health)
        } catch (error) {
            console.error('Backend health check failed:', error)
            setBackendStatus('error')
        }
    }

    const handleSessionSelect = (sessionId: string) => {
        setCurrentSessionId(sessionId)
        setShowConversation(true)
        setHomeMode('CHAT_EXISTING') // Ensure we're in the right mode to show SessionChat
    }

    const handleNewSession = () => {
        // Reset state and return to landing page so user can choose chat type
        setCurrentSessionId(undefined)
        setCurrentSession(null)
        setShowConversation(false)  // Hide conversation view & sidebar
        setHomeMode('HOME')         // Show landing selector (Create index / Chat with index / LLM Chat)
    }

    const handleSessionChange = async (session: ChatSession) => {
        setCurrentSession(session)

        // Update the current session ID if it changed (e.g., brand-new session)
        if (session.id !== currentSessionId) {
            setCurrentSessionId(session.id)
        }

        // Always refresh the sidebar so that updated titles / message counts are displayed
            if (sidebarRef) {
                await sidebarRef.refreshSessions()
        }
    }

    const handleSessionDelete = (deletedSessionId: string) => {
        if (currentSessionId === deletedSessionId) {
            // Stay in conversation mode but show empty state
            setCurrentSessionId(undefined)
            setCurrentSession(null)
        }
    }

    const handleStartConversation = () => {
        if (backendStatus === 'connected') {
            // Just show empty state, don't create session yet
            handleNewSession()
        } else {
            setShowConversation(true)
        }
    }

    return (
        <div className="flex h-full w-full flex-col">
            {/* Top App Bar */}
            <header className="h-12 relative flex items-center justify-center border-b border-gray-800 flex-shrink-0 bg-red-800/80">
                {(homeMode === 'CHAT_EXISTING' || homeMode === 'QUICK_CHAT') && <button onClick={()=>setSidebarOpen(o=>!o)} className="absolute left-4 p-1 rounded hover:cursor-pointer hover:bg-red-800 text-gray-200 focus:outline-none" title="Toggle sidebar">
                    {sidebarOpen ? <span className="text-xl leading-none"> <PanelLeftClose className="w-5 h-5"/></span> : <PanelLeftOpen className="w-5 h-5" />}
                </button>}
                {homeMode !== 'HOME' && (
                    <h1 className="text-lg font-semibold text-white">Academic RAG</h1>
                )}
            </header>
            {/* Main content row */}
            <div className="flex flex-1 flex-row min-h-0">
                {/* Session Sidebar */}
                {sidebarOpen && showConversation && (homeMode === 'CHAT_EXISTING' || homeMode === 'QUICK_CHAT') && (
                    <SessionSidebar
                        currentSessionId={currentSessionId}
                        onSessionSelect={handleSessionSelect}
                        onNewSession={handleNewSession}
                        onSessionDelete={handleSessionDelete}
                        onSessionCreated={setSidebarRef}
                    />
                )}
                
                <main className="flex flex-1 flex-col transition-all duration-200 min-h-0 overflow-hidden">
                    {homeMode === 'HOME' ? (
                        <div className="flex items-center justify-center h-full">
                            <div className="space-y-8">
                                <div className="text-center space-y-2">
                                    <h1 className="text-4xl font-bold">Academic Info</h1>
                                    <p className="text-lg text-gray-400">What can I find for you today?</p>
                                </div>

                                <LandingMenu onSelect={(m)=>{
                                    if(m==='CHAT_EXISTING'){ setShowIndexPicker(true); return; }
                                    if(m==='QUICK_CHAT'){
                                        setHomeMode('QUICK_CHAT');
                                        setShowConversation(true);
                                        return;
                                    }
                                    setHomeMode('INDEX');
                                }} />
                                <div className="flex flex-col items-center gap-3 mt-12">
                                    <div className="flex items-center gap-2 text-sm">
                                        {backendStatus === 'checking' && (
                                            <div className="flex items-center gap-2 text-gray-400">
                                                <div className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse"></div>
                                                Making a backend connection...
                                            </div>
                                        )}
                                        {backendStatus === 'connected' && (
                                            <div className="flex items-center gap-2 text-green-400">
                                                <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                                                Backend connected  Session-based chat ready
                                            </div>
                                        )}
                                        {backendStatus === 'error' && (
                                            <div className="flex items-center gap-2 text-red-400">
                                                <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                                                Offline backend  Launch the backend server to make chat available.
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    ) : homeMode==='CHAT_EXISTING' ? (
                        <SessionChat
                            sessionId={currentSessionId}
                            onSessionChange={handleSessionChange}
                            className="flex-1"
                        />
                    ) : homeMode==='QUICK_CHAT' ? (
                        <QuickChat sessionId={currentSessionId} onSessionChange={handleSessionChange} className="flex-1" />
                    ) : null}
                </main>

                {homeMode==='INDEX' && (
                  <div className="fixed inset-0 flex items-center justify-center backdrop-blur-lg z-50 p-4">
                    <IndexForm onClose={()=>setHomeMode('HOME')} onIndexed={(s)=>{setHomeMode('CHAT_EXISTING'); handleSessionSelect(s.id);}} />
                  </div>
                )}

                {showIndexInfo && currentSessionId && (
                  <SessionIndexInfo sessionId={currentSessionId} onClose={()=>setShowIndexInfo(false)} />
                )}

                {showIndexPicker && (
                  <IndexPicker onClose={()=>setShowIndexPicker(false)} onSelect={async (idxId)=>{
                    // create session and link index then open chat
                    const session = await chatAPI.createSession()
                    await chatAPI.linkIndexToSession(session.id, idxId)
                    setShowIndexPicker(false)
                    setHomeMode('CHAT_EXISTING')
                    handleSessionSelect(session.id)
                  }} />
                )}
            </div>
        </div>
    );
} 