"use client"

import * as React from "react"
import { useRef, useEffect, useState } from "react"
import {
  ChatBubbleAvatar,
} from "@/components/ui/chat-bubble"
import { Copy, RefreshCcw, MoreHorizontal, ChevronDown, Loader2, CheckCircle, XOctagon } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ChatMessage, Step } from "@/lib/api"
import Markdown from "@/components/Markdown"
import { normalizeWhitespace } from "@/utils/textNormalization"

interface ConversationPageProps {
  messages: ChatMessage[]
  isLoading?: boolean
  className?: string
  onAction?: (action: string, messageId: string, messageContent: string) => void
}

const actionIcons = [
  { icon: Copy, type: "Copy", action: "copy" },
  // { icon: ThumbsUp, type: "Like", action: "like" },
  // { icon: ThumbsDown, type: "Dislike", action: "dislike" },
  // { icon: Volume2, type: "Speak", action: "speak" },
  { icon: RefreshCcw, type: "Regenerate", action: "regenerate" },
  // { icon: MoreHorizontal, type: "More", action: "more" },
]

type CitationDoc = {
  text?: string
  chunk_id?: string | number
  rerank_score?: number
  score?: number
  _distance?: number
  [key: string]: unknown
}

type StepStatus = 'pending' | 'active' | 'done' | 'error'

type StructuredStep = {
  key?: string
  label?: string
  status?: StepStatus
  details?: unknown
  [key: string]: unknown
}

type StructuredContent = Array<Record<string, unknown>> | { steps: Step[] }

type SubAnswerDetail = {
  question: string
  answer: string
  source_documents?: CitationDoc[]
}

const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isStructuredStepsContainer = (content: ChatMessage['content']): content is { steps: Step[] } =>
  isObjectRecord(content) && Array.isArray(content.steps)

const asStructuredSteps = (content: StructuredContent): StructuredStep[] =>
  (Array.isArray(content) ? content : content.steps) as unknown as StructuredStep[]

const toCitationDoc = (value: unknown): CitationDoc | null => {
  if (!isObjectRecord(value)) return null
  return value as CitationDoc
}

const toSubAnswerDetail = (value: unknown): SubAnswerDetail | null => {
  if (!isObjectRecord(value)) return null
  const question = typeof value.question === 'string' ? value.question : ''
  const answer = typeof value.answer === 'string' ? value.answer : ''
  const source_documents = Array.isArray(value.source_documents)
    ? value.source_documents.map(toCitationDoc).filter((doc): doc is CitationDoc => doc !== null)
    : undefined
  if (!question) return null
  return { question, answer, source_documents }
}

const extractTextFromMessageContent = (messageContent: ChatMessage['content']): string => {
  if (typeof messageContent === 'string') return messageContent

  if (Array.isArray(messageContent)) {
    return messageContent
      .map((segment) => {
        if (!isObjectRecord(segment)) return ''
        const text = typeof segment.text === 'string' ? segment.text : ''
        const answer = typeof segment.answer === 'string' ? segment.answer : ''
        return text || answer
      })
      .join('\n')
  }

  if (isStructuredStepsContainer(messageContent)) {
    return messageContent.steps
      .map((step) => `${step.label}${typeof step.details === 'string' ? `: ${step.details}` : ''}`)
      .join('\n')
  }

  return ''
}

// Citation block toggle component
function Citation({ doc, idx }: { doc: CitationDoc, idx: number }) {
  const [open,setOpen]=React.useState(false);
  const docText = typeof doc.text === 'string' ? doc.text : ''
  const preview = docText.replace(/\s+/g,' ').trim().slice(0,160) + (docText.length>160?'':'');
  return (
    <div onClick={()=>setOpen(!open)} className="text-xs text-gray-300 bg-gray-900/60 rounded p-2 cursor-pointer hover:bg-gray-800 transition">
      <span className="font-semibold mr-1">[{idx+1}]</span>{open ? docText : preview}
    </div>
  );
}

// NEW: Expandable list of citations per assistant message
function CitationsBlock({ docs }: { docs: CitationDoc[] }) {
  const scored = React.useMemo(() => {
    const filtered = docs.filter(d => typeof d?.rerank_score === 'number' || typeof d?.score === 'number' || typeof d?._distance === 'number')
    return filtered.sort(
      (a, b) =>
        (b.rerank_score ?? b.score ?? (typeof b._distance === 'number' && b._distance !== 0 ? 1 / b._distance : 0)) -
        (a.rerank_score ?? a.score ?? (typeof a._distance === 'number' && a._distance !== 0 ? 1 / a._distance : 0))
    )
  }, [docs])
  const [expanded, setExpanded] = useState(false);

  if (scored.length === 0) return null;

  const visibleDocs = expanded ? scored : scored.slice(0, 5);

  return (
    <div className="mt-2 text-xs text-gray-400">
      <p className="font-semibold mb-1">Sources:</p>
      <div className="grid grid-cols-1 gap-2">
        {visibleDocs.map((doc, i) => <Citation key={doc.chunk_id || i} doc={doc} idx={i} />)}
      </div>
      {scored.length > 5 && (
        <button 
          onClick={() => setExpanded(!expanded)} 
          className="text-blue-400 hover:text-blue-300 mt-2 text-xs"
        >
          {expanded ? 'Show less' : `Show ${scored.length-5} more`}
        </button>
      )}
    </div>
  );
}

function StepIcon({ status }: { status: 'pending' | 'active' | 'done' | 'error' }) {
  switch (status) {
    case 'pending':
      return <MoreHorizontal className="w-4 h-4 text-neutral-600" />
    case 'active':
      return <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
    case 'done':
      return <CheckCircle className="w-4 h-4 text-green-400" />
    case 'error':
      return <XOctagon className="w-4 h-4 text-red-400" />
    default:
      return null
  }
}

const statusBorder: Record<string, string> = {
  pending: 'border-neutral-800',
  active: 'border-blue-400 animate-pulse',
  done: 'border-green-400',
  error: 'border-red-400'
}

// Component to handle <think> tokens and render them in a collapsible block
function ThinkingText({ text }: { text: string }) {
  const regex = /<think>([\s\S]*?)<\/think>/g;
  const thinkSegments: string[] = [];
  const visibleText = text.replace(regex, (_, p1) => {
    thinkSegments.push(p1.trim());
    return ""; // remove thinking content from main text
  });

  return (
    <>
      {thinkSegments.length > 0 && (
        <details className="thinking-block inline-block align-baseline mr-2" open={false}>
          <summary className="cursor-pointer text-xs text-gray-400 uppercase select-none">Thinking</summary>
          <div className="mt-1 space-y-1 text-xs text-gray-400 italic">
            {thinkSegments.map((seg, idx) => (
              <div key={idx}>{seg}</div>
            ))}
          </div>
        </details>
      )}
      {visibleText.trim() && (
        <Markdown text={normalizeWhitespace(visibleText)} className="whitespace-pre-wrap" />
      )}
    </>
  );
}

function StructuredMessageBlock({
  content,
  hideCitations = false,
}: {
  content: StructuredContent
  hideCitations?: boolean
}) {
  const steps = asStructuredSteps(content)
  const finalStep = steps.find((step) => step.key === 'final')
  const hasSubAnswers = steps.some((step) => step.key === 'answer' && Array.isArray(step.details) && step.details.length > 0)

  // If final answer is reached, only show the final step
  if (finalStep && finalStep.status && finalStep.status !== 'pending') {
    const borderCls = statusBorder[finalStep.status] || statusBorder['pending'];
    const statusClass = `timeline-card bg-white/25 shadow-sm card my-1 py-2 pl-3 pr-2 rounded border-l-2 ${borderCls}`;
    return (
      <div className="flex flex-col">
        <div className={statusClass}>
          <div className="flex items-center gap-2 mb-1">
            <StepIcon status={finalStep.status ?? 'pending'} />
            <span className="text-sm font-medium text-black">{finalStep.label}</span>
          </div>
          {/* Details for final step only */}
          {isObjectRecord(finalStep.details) ? (
            <div className="space-y-3">
              <div className="whitespace-pre-wrap">
                <ThinkingText text={normalizeWhitespace(typeof finalStep.details.answer === 'string' ? finalStep.details.answer : '')} />
              </div>
              {/* {!hideCitations && !hasSubAnswers && Array.isArray(finalStep.details.source_documents) && finalStep.details.source_documents.length > 0 && (
                <CitationsBlock docs={finalStep.details.source_documents.map(toCitationDoc).filter((doc): doc is CitationDoc => doc !== null)} />
              )} */}
            </div>
          ) : finalStep.details && typeof finalStep.details === 'string' ? (
            <div className="whitespace-pre-wrap">
              <ThinkingText text={normalizeWhitespace(finalStep.details)} />
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  // Otherwise, show each step process (excluding final if not reached)
  // Compute the last index that has started (status !== 'pending')
  const lastRevealedIdx = (() => {
    for (let i = steps.length - 1; i >= 0; i--) {
      if (steps[i].status && steps[i].status !== 'pending') {
        return i;
      }
    }
    return -1;
  })();
  const visibleSteps = lastRevealedIdx >= 0 ? steps.slice(0, lastRevealedIdx + 1) : [];

  return (
    <div className="flex flex-col">
      {visibleSteps.map((step, index: number) => {
        if (step.key && step.label && step.key !== 'final') {
          const stepStatus = step.status ?? 'pending';
          const borderCls = statusBorder[stepStatus] || statusBorder['pending'];
          const statusClass = `timeline-card bg-white/25 shadow-sm card my-1 py-2 pl-3 pr-2 rounded border-l-2 ${borderCls}`;
          return (
            <div key={step.key} className={statusClass}>
              <div className="flex items-center gap-2 mb-1">
                <StepIcon status={step.status ?? 'pending'} />
                <span className="text-sm font-medium text-black">{step.label}</span>
              </div>
              {/* Details for each step */}
              {Array.isArray(step.details) ? (
                step.key === 'decompose' && step.details.every((detail) => typeof detail === 'string') ? (
                  <ul className="list-disc list-inside space-y-1">
                    {step.details.map((q: string, idx:number)=>(
                      <li key={idx}>{q}</li>
                    ))}
                  </ul>
                ) : (
                  <div className="space-y-2">
                    {step.details.map((detail, idx: number) => {
                      const parsed = toSubAnswerDetail(detail)
                      if (!parsed) return null
                      return (
                      <div key={idx} className="border-l-2 border-blue-400 pl-2">
                        <div className="font-semibold">{parsed.question}</div>
                        <div><ThinkingText text={normalizeWhitespace(parsed.answer)} /></div>
                        {!hideCitations && Array.isArray(parsed.source_documents) && parsed.source_documents.length > 0 && (
                          <CitationsBlock docs={parsed.source_documents} />
                        )}
                      </div>
                      )
                    })}
                  </div>
                )
              ) : (
                <ThinkingText text={normalizeWhitespace(step.details as string)} />
              )}
            </div>
          );
        }
        return null;
      })}
    </div>
  );
}

export function ConversationPage({ 
  messages, 
  isLoading = false,
  className = "",
  onAction
}: ConversationPageProps) {
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [showScrollButton, setShowScrollButton] = useState(false)
  const [isUserNearBottom,setIsUserNearBottom]=useState(true)

  // Track if user is near bottom so we don't interrupt manual scrolling
  useEffect(() => {
    if(isUserNearBottom){
    scrollToBottom()
    }
  }, [messages, isLoading])

  // Monitor scroll position to show/hide scroll button
  useEffect(() => {
    const scrollContainer = scrollAreaRef.current?.querySelector('[data-radix-scroll-area-viewport]')
    if (!scrollContainer) return

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = scrollContainer
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100
      setShowScrollButton(!isNearBottom)
      setIsUserNearBottom(isNearBottom)
    }

    scrollContainer.addEventListener('scroll', handleScroll)
    handleScroll() // Check initial state

    return () => scrollContainer.removeEventListener('scroll', handleScroll)
  }, [])

  const scrollToBottom = () => {
    // Try multiple methods to ensure scrolling works
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
    
    // Fallback: scroll the container directly
    setTimeout(() => {
      if (scrollAreaRef.current) {
        const scrollContainer = scrollAreaRef.current.querySelector('[data-radix-scroll-area-viewport]') || scrollAreaRef.current
        if (scrollContainer) {
          scrollContainer.scrollTop = scrollContainer.scrollHeight
        }
      }
    }, 100)
  }

  const handleAction = (action: string, messageId: string, messageContent: string) => {
    if (onAction) {
      // For structured messages, we'll just join the text parts for copy/paste
      const contentToPass = messageContent;
      onAction(action, messageId, contentToPass)
      return
    }
    
    console.log(`Action ${action} clicked for message ${messageId}`)
    // Handle different actions here
    switch (action) {
      case 'copy':
        navigator.clipboard.writeText(messageContent)
        break
      case 'regenerate':
        // Regenerate AI response
        break
      case 'like':
        // Add like reaction
        break
      case 'dislike':
        // Add dislike reaction
        break
      case 'speak':
        // Text to speech
        break
      case 'more':
        // Show more options
        break
    }
  }

  return (
    <div className={`flex flex-col h-full  relative overflow-hidden ${className}`}>
      <ScrollArea ref={scrollAreaRef} className="flex-1 h-full px-4 pt-4 pb-6 min-h-0">
        <div className="max-w-4xl mx-auto space-y-6">
          {messages.map((message) => {
            const isUser = message.sender === "user"
            const metadata = message.metadata
            const sourceDocs = Array.isArray(metadata?.source_documents)
              ? metadata.source_documents.map(toCitationDoc).filter((doc): doc is CitationDoc => doc !== null)
              : []

            // If we have a placeholder "loading" message, hide it and rely on the global loader.
            if (message.isLoading) return null

            const steps = isStructuredStepsContainer(message.content)
              ? message.content.steps
              : undefined

            const finalOrDirectStep = steps?.find(
              (step) => step?.key === 'final' || step?.key === 'direct'
            )

            // Streaming can continue after global isLoading flips false; treat assistant message
            // as "complete" only once the final/direct step is done, or backend marks it complete.
            const isAssistantMessageComplete =
              isUser ||
              metadata?.message_type === 'complete' ||
              !steps ||
              finalOrDirectStep?.status === 'done'

            const isAssistantMessageInProgress = !isAssistantMessageComplete

            const shouldShowActions =
              !isUser &&
              !isLoading &&
              !isAssistantMessageInProgress
            const shouldShowCitations =
              !isUser &&
              !isLoading &&
              !isAssistantMessageInProgress &&
              typeof message.content === 'string' &&
              Array.isArray(sourceDocs) &&
              sourceDocs.length > 0
            
            return (
              <div key={message.id} className="w-full group">
                <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
                  {!isUser && (
                    <ChatBubbleAvatar 
                      src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiIGNsYXNzPSJsdWNpZGUgbHVjaWRlLWJvdC1pY29uIGx1Y2lkZS1ib3QiPjxwYXRoIGQ9Ik0xMiA4VjRIOCIvPjxyZWN0IHdpZHRoPSIxNiIgaGVpZ2h0PSIxMiIgeD0iNCIgeT0iOCIgcng9IjIiLz48cGF0aCBkPSJNMiAxNGgyIi8+PHBhdGggZD0iTTIwIDE0aDIiLz48cGF0aCBkPSJNMTUgMTN2MiIvPjxwYXRoIGQ9Ik05IDEzdjIiLz48L3N2Zz4="
                      className="mt-1 flex-shrink-0"
                    />
                  )}
                  
                  <div className={`flex flex-col space-y-2 ${isUser ? 'items-end' : 'items-start'} max-w-full md:max-w-3xl`}>
                    <div
                      className={`rounded-2xl px-5 py-4 ${isUser ? "bg-black/5" : "bg-black/5"}`}
                    >
                      <div className="whitespace-pre-wrap text-base leading-relaxed">
                        {typeof message.content === 'string' 
                            ? <ThinkingText text={normalizeWhitespace(message.content)} />
                            : <StructuredMessageBlock content={message.content} hideCitations={isAssistantMessageInProgress} />
                        }
                      </div>
                    </div>
                    
                    {shouldShowActions && (
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                        {actionIcons.map(({ icon: Icon, type, action }) => (
                          <button
                            key={action}
                            onClick={() => {
                              const content = extractTextFromMessageContent(message.content)
                              handleAction(action, message.id, content)
                            }}
                            className="p-1.5 hover:bg-gray-700 rounded-md transition-colors text-gray-400 hover:text-gray-200"
                            title={type}
                          >
                            <Icon className="w-3.5 h-3.5" />
                          </button>
                        ))}
                      </div>
                    )}

                    {/* Global citations only for plain-string messages */}
                    {shouldShowCitations && (
                      <CitationsBlock docs={sourceDocs} />
                    )}
                  </div>

                  {isUser && (
                    <ChatBubbleAvatar 
                      className="mt-1 flex-shrink-0"
                      src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiIGNsYXNzPSJsdWNpZGUgbHVjaWRlLXVzZXItcm91bmQtaWNvbiBsdWNpZGUtdXNlci1yb3VuZCI+PGNpcmNsZSBjeD0iMTIiIGN5PSI4IiByPSI1Ii8+PHBhdGggZD0iTTIwIDIxYTggOCAwIDAgMC0xNiAwIi8+PC9zdmc+"
                      fallback="User"
                    />
                  )}
                </div>
              </div>
            )
          })}
          
          {/* Loading indicator for new message */}
          {isLoading && (
            <div className="w-full group">
              <div className="flex gap-3 justify-start">
                <ChatBubbleAvatar fallback="AI" className="mt-1 flex-shrink-0" />
                <div className="flex flex-col space-y-2 items-start max-w-[80%]">
                  <div className="rounded-2xl px-4 py-3 ">
                    <div className="flex items-center space-x-2">
                      <div className="flex space-x-1">
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{animationDelay: '0.1s'}}></div>
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
                      )}
          
          {/* Invisible element to scroll to */}
          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>
      
      {/* Scroll to bottom button - only show when not at bottom */}
      {showScrollButton && (
        <div className="absolute bottom-20 left-1/2 transform -translate-x-1/2 z-10">
          <button
            onClick={scrollToBottom}
            className="p-2 bg-gray-800 border border-gray-700 rounded-full hover:bg-gray-700 transition-all duration-200 shadow-lg group animate-in fade-in slide-in-from-bottom-2"
            title="Scroll to bottom"
          >
            <ChevronDown className="w-4 h-4 text-gray-400 group-hover:text-gray-200 transition-colors" />
          </button>
        </div>
      )}
    </div>
  )
}  