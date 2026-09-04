import {
  useState,
  useEffect,
  useRef,
} from 'react';
import ReactMarkdown from 'react-markdown';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import MemoryUsed from './MemoryUsed';
import './ChatInterface.css';


export default function ChatInterface({
  conversation,
  onSendMessage,
  isLoading,
}) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({
      behavior: 'smooth',
    });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  const handleSubmit = (event) => {
    event.preventDefault();

    if (input.trim() && !isLoading) {
      onSendMessage(input);
      setInput('');
    }
  };

  const handleKeyDown = (event) => {
    if (
      event.key === 'Enter'
      && !event.shiftKey
    ) {
      event.preventDefault();
      handleSubmit(event);
    }
  };

  if (!conversation) {
    return (
      <div className="chat-interface">
        <div className="empty-state">
          <h2>Welcome to LLM Council</h2>
          <p>
            Create a new conversation to get started
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-interface">
      <div className="messages-container">
        {conversation.messages.length === 0 ? (
          <div className="empty-state">
            <h2>Start a conversation</h2>

            <p>
              Ask a question to consult the LLM Council
            </p>
          </div>
        ) : (
          conversation.messages.map(
            (message, index) => (
              <div
                key={index}
                className="message-group"
              >
                {message.role === 'user' ? (
                  <div className="user-message">
                    <div className="message-label">
                      You
                    </div>

                    <div className="message-content">
                      <div className="markdown-content">
                        <ReactMarkdown>
                          {message.content}
                        </ReactMarkdown>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="assistant-message">
                    <div className="message-label">
                      LLM Council
                    </div>

                    {message.loading?.stage1 && (
                      <div className="stage-loading">
                        <div className="spinner" />

                        <span>
                          Running Stage 1: Collecting
                          individual responses...
                        </span>
                      </div>
                    )}

                    {message.stage1 && (
                      <Stage1
                        responses={message.stage1}
                      />
                    )}

                    {message.loading?.stage2 && (
                      <div className="stage-loading">
                        <div className="spinner" />

                        <span>
                          Running Stage 2: Peer rankings...
                        </span>
                      </div>
                    )}

                    {message.stage2 && (
                      <Stage2
                        rankings={message.stage2}
                        labelToModel={
                          message.metadata
                            ?.label_to_model
                        }
                        aggregateRankings={
                          message.metadata
                            ?.aggregate_rankings
                        }
                      />
                    )}

                    {message.loading?.stage3 && (
                      <div className="stage-loading">
                        <div className="spinner" />

                        <span>
                          Running Stage 3: Final
                          synthesis...
                        </span>
                      </div>
                    )}

                    {message.stage3 && (
                      <Stage3
                        finalResponse={message.stage3}
                      />
                    )}

                    {message.stage3
                      && message.metadata?.knowledge && (
                        <MemoryUsed
                          knowledge={
                            message.metadata.knowledge
                          }
                        />
                      )}
                  </div>
                )}
              </div>
            )
          )
        )}

        {isLoading && (
          <div className="loading-indicator">
            <div className="spinner" />

            <span>
              Consulting the council...
            </span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {conversation.messages.length === 0 && (
        <form
          className="input-form"
          onSubmit={handleSubmit}
        >
          <textarea
            className="message-input"
            placeholder={
              'Ask your question... '
              + '(Shift+Enter for new line, '
              + 'Enter to send)'
            }
            value={input}
            onChange={(event) => {
              setInput(event.target.value);
            }}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            rows={3}
          />

          <button
            type="submit"
            className="send-button"
            disabled={
              !input.trim() || isLoading
            }
          >
            Send
          </button>
        </form>
      )}
    </div>
  );
}