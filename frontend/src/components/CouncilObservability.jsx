import { getModelDisplayName } from '../modelNames';
import './CouncilObservability.css';


function toLabel(value) {
  if (!value) {
    return 'Unknown';
  }

  const special = {
    github: 'GitHub',
    wix: 'Wix',
    web: 'Web',
    supplier_marketplace: 'Supplier Marketplace',
  };

  if (special[value]) {
    return special[value];
  }

  return String(value)
    .split(/[-_ ]+/)
    .filter(Boolean)
    .map((word) => (
      word.charAt(0).toUpperCase()
      + word.slice(1)
    ))
    .join(' ');
}


function formatTimestamp(value) {
  if (!value) {
    return 'Observation time unavailable';
  }

  const timestamp = new Date(value);

  if (Number.isNaN(timestamp.getTime())) {
    return value;
  }

  return timestamp.toLocaleString();
}


function specialistSummary(specialists) {
  const assignments = Array.isArray(
    specialists?.assignments
  )
    ? specialists.assignments
    : [];

  const responded = assignments.filter(
    (assignment) => assignment.responded
  ).length;

  return {
    assignments,
    responded,
    total: assignments.length,
  };
}


function hasAccessActivity(access) {
  if (!access) {
    return false;
  }

  return Boolean(
    access.blocked_by_user
    || access.degraded
    || access.mode !== 'none'
    || access.required
    || (access.requested_capabilities || []).length
    || (access.sources_used || []).length
    || (access.failures || []).length
  );
}


function SpecialistsPanel({ specialists }) {
  if (!specialists) {
    return null;
  }

  const {
    assignments,
    responded,
    total,
  } = specialistSummary(specialists);

  const status = specialists.degraded
    ? 'Degraded'
    : 'Healthy';

  return (
    <details className="observability-card">
      <summary className="observability-summary">
        <span
          className={`observability-dot ${
            specialists.degraded
              ? 'observability-dot-warning'
              : 'observability-dot-success'
          }`}
        />

        <span className="observability-title">
          Specialist Routing
        </span>

        <span className="observability-count">
          {responded}/{total || 0} responded
        </span>

        <span
          className={`observability-status ${
            specialists.degraded
              ? 'observability-status-warning'
              : 'observability-status-success'
          }`}
        >
          {status}
        </span>
      </summary>

      <div className="observability-content">
        <div className="observability-description">
          Deterministic specialist seats selected for this
          Council run. A failed seat is preserved rather than
          silently replaced.
        </div>

        <div className="observability-meta-grid">
          <div className="observability-meta">
            <span className="observability-meta-value">
              {specialists.router_version || 'Unknown'}
            </span>
            <span className="observability-meta-label">
              Router
            </span>
          </div>

          <div className="observability-meta">
            <span className="observability-meta-value">
              {specialists.defaulted ? 'Default' : 'Signalled'}
            </span>
            <span className="observability-meta-label">
              Route selection
            </span>
          </div>

          <div className="observability-meta">
            <span className="observability-meta-value">
              {responded}/{total || 0}
            </span>
            <span className="observability-meta-label">
              Seats responded
            </span>
          </div>
        </div>

        <div className="observability-list">
          {assignments.map((assignment) => (
            <div
              className="observability-row"
              key={
                assignment.seat
                || assignment.role_id
                || assignment.model
              }
            >
              <span className="observability-seat">
                Seat {assignment.seat || '?'}
              </span>

              <div className="observability-row-details">
                <div className="observability-row-title">
                  {assignment.role_name
                    || toLabel(assignment.role_id)}
                </div>

                <div className="observability-row-subtitle">
                  {getModelDisplayName(assignment.model)}
                </div>
              </div>

              <span
                className={`observability-response ${
                  assignment.responded
                    ? 'observability-response-success'
                    : 'observability-response-failed'
                }`}
              >
                {assignment.responded
                  ? 'Responded'
                  : 'No response'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </details>
  );
}


function AccessPanel({ access }) {
  if (!hasAccessActivity(access)) {
    return null;
  }

  const requested = Array.isArray(
    access.requested_capabilities
  )
    ? access.requested_capabilities
    : [];

  const sources = Array.isArray(access.sources_used)
    ? access.sources_used
    : [];

  const failures = Array.isArray(access.failures)
    ? access.failures
    : [];

  const blocked = Boolean(access.blocked_by_user);
  const degraded = Boolean(access.degraded);

  let status = 'Completed';
  let statusClass = 'observability-status-success';
  let dotClass = 'observability-dot-success';

  if (blocked) {
    status = 'Blocked';
    statusClass = 'observability-status-neutral';
    dotClass = 'observability-dot-neutral';
  } else if (degraded) {
    status = 'Degraded';
    statusClass = 'observability-status-warning';
    dotClass = 'observability-dot-warning';
  } else if (!sources.length) {
    status = 'Planned';
    statusClass = 'observability-status-neutral';
    dotClass = 'observability-dot-neutral';
  }

  return (
    <details className="observability-card">
      <summary className="observability-summary">
        <span
          className={`observability-dot ${dotClass}`}
        />

        <span className="observability-title">
          Controlled Access
        </span>

        <span className="observability-count">
          {sources.length}{' '}
          {sources.length === 1 ? 'source' : 'sources'}
        </span>

        <span
          className={`observability-status ${statusClass}`}
        >
          {status}
        </span>
      </summary>

      <div className="observability-content">
        <div className="observability-description">
          External access planned by the controlled access
          layer. Source bodies are not persisted in this
          metadata.
        </div>

        <div className="observability-meta-grid">
          <div className="observability-meta">
            <span className="observability-meta-value">
              {toLabel(access.mode || 'none')}
            </span>
            <span className="observability-meta-label">
              Access mode
            </span>
          </div>

          <div className="observability-meta">
            <span className="observability-meta-value">
              {requested.length}
            </span>
            <span className="observability-meta-label">
              Capabilities requested
            </span>
          </div>

          <div className="observability-meta">
            <span className="observability-meta-value">
              {sources.length}
            </span>
            <span className="observability-meta-label">
              Sources used
            </span>
          </div>
        </div>

        {requested.length > 0 && (
          <div className="observability-capabilities">
            {requested.map((capability) => (
              <span
                className="observability-capability"
                key={capability}
              >
                {toLabel(capability)}
              </span>
            ))}
          </div>
        )}

        {blocked && (
          <div className="observability-notice">
            External access was blocked by the user for this
            request.
          </div>
        )}

        {sources.length > 0 && (
          <div className="observability-list">
            {sources.map((source, index) => (
              <div
                className="observability-source"
                key={
                  source.locator
                  || `${source.capability}-${index}`
                }
              >
                <span className="observability-source-type">
                  {toLabel(source.capability)}
                </span>

                <div className="observability-row-details">
                  <div className="observability-row-title">
                    {source.source_name
                      || toLabel(source.capability)}
                  </div>

                  <div className="observability-source-locator">
                    {source.locator
                      || 'Locator unavailable'}
                  </div>

                  <div className="observability-source-time">
                    {formatTimestamp(source.observed_at)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {failures.length > 0 && (
          <div className="observability-failures">
            <div className="observability-section-label">
              Access failures
            </div>

            {failures.map((failure, index) => (
              <div
                className="observability-failure"
                key={`${failure.capability}-${index}`}
              >
                <span>
                  {toLabel(failure.capability)}
                </span>
                <code>
                  {failure.code || 'provider_error'}
                </code>
              </div>
            ))}
          </div>
        )}
      </div>
    </details>
  );
}


export default function CouncilObservability({
  specialists,
  access,
}) {
  if (!specialists && !hasAccessActivity(access)) {
    return null;
  }

  return (
    <div className="council-observability">
      <SpecialistsPanel specialists={specialists} />
      <AccessPanel access={access} />
    </div>
  );
}
