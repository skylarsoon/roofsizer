import { Building2 } from 'lucide-react';

export default function ImagePreview({ results, loading }) {
  if (loading) {
    return <div className="image-preview image-preview-loading" aria-label="Loading satellite view" />;
  }

  if (!results) {
    return (
      <div className="image-preview image-preview-empty">
        <Building2 size={28} strokeWidth={1.6} aria-hidden="true" />
        <p>Satellite view loads here</p>
      </div>
    );
  }

  return (
    <div className="image-preview image-preview-results">
      {results.satelliteImageUrl ? (
        <img
          src={results.satelliteImageUrl}
          alt="Satellite view of property"
          className="image-preview-photo"
        />
      ) : null}
    </div>
  );
}
