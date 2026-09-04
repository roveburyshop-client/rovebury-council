import './MemoryUsed.css';


function toTitleCase(value) {
  const specialWords = {
    rovebury: 'ROVEBURY',
    wix: 'Wix',
    aliexpress: 'AliExpress',
    uk: 'UK',
    seo: 'SEO',
  };

  return value
    .split(/[-_ ]+/)
    .filter(Boolean)
    .map((word) => {
      const normalized = word.toLowerCase();

      if (specialWords[normalized]) {
        return specialWords[normalized];
      }

      return (
        normalized.charAt(0).toUpperCase()
        + normalized.slice(1)
      );
    })
    .join(' ');
}


function formatSourceName(source) {
  const filename = source.split('/').pop() || source;

  const baseName = filename.replace(
    /\.md$/i,
    ''
  );

  const decisionMatch = baseName.match(
    /^(DEC-\d+)-(.+)$/i
  );

  if (decisionMatch) {
    return (
      `${decisionMatch[1].toUpperCase()} · `
      + toTitleCase(decisionMatch[2])
    );
  }

  return toTitleCase(baseName);
}


function getSourceType(source) {
  if (source.startsWith('decisions/')) {
    return 'Decision';
  }

  if (source.startsWith('memory/entities/')) {
    return 'Entity';
  }

  if (source.startsWith('memory/relationships/')) {
    return 'Relationship';
  }

  if (source.startsWith('research/')) {
    return 'Research';
  }

  if (source.startsWith('seo/')) {
    return 'SEO';
  }

  if (source.startsWith('products/')) {
    return 'Product';
  }

  if (source.startsWith('market/')) {
    return 'Market';
  }

  if (source.startsWith('brand/')) {
    return 'Brand';
  }

  if (source.startsWith('website/')) {
    return 'Website';
  }

  return 'Knowledge';
}


export default function MemoryUsed({ knowledge }) {
  if (!knowledge) {
    return null;
  }

  const sources = Array.isArray(knowledge.sources)
    ? knowledge.sources
    : [];

  if (!knowledge.used) {
    return (
      <div className="memory-unused">
        <span className="memory-dot memory-dot-neutral" />

        <div>
          <div className="memory-unused-title">
            ROVEBURY Memory
          </div>

          <div className="memory-unused-text">
            No internal knowledge was used for this response.
          </div>
        </div>
      </div>
    );
  }

  return (
    <details className="memory-used">
      <summary className="memory-summary">
        <span className="memory-dot" />

        <span className="memory-summary-title">
          Memory Used
        </span>

        <span className="memory-summary-count">
          {sources.length}{' '}
          {sources.length === 1 ? 'source' : 'sources'}
        </span>

        <span className="memory-summary-action">
          View sources
        </span>
      </summary>

      <div className="memory-content">
        <div className="memory-description">
          Internal ROVEBURY knowledge retrieved for this
          Council response.
        </div>

        <div className="memory-stats">
          <div className="memory-stat">
            <span className="memory-stat-value">
              {sources.length}
            </span>

            <span className="memory-stat-label">
              Sources
            </span>
          </div>

          <div className="memory-stat">
            <span className="memory-stat-value">
              {Number(
                knowledge.characters || 0
              ).toLocaleString()}
            </span>

            <span className="memory-stat-label">
              Context characters
            </span>
          </div>
        </div>

        <div className="memory-source-list">
          {sources.map((source) => (
            <div
              key={source}
              className="memory-source"
            >
              <span className="memory-source-type">
                {getSourceType(source)}
              </span>

              <div className="memory-source-details">
                <div className="memory-source-name">
                  {formatSourceName(source)}
                </div>

                <div className="memory-source-path">
                  {source}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </details>
  );
}