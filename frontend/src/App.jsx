import { useState, useRef } from "react";
import "./App.css";

const DOC_TYPES = [
  { value: "generic", label: "Generic" },
  { value: "gst_certificate", label: "GST Certificate" },
  { value: "pan_card", label: "PAN Card" },
  { value: "udyam_registration", label: "Udyam Registration" },
  { value: "mca21_incorporation", label: "MCA21 Incorporation" },
  { value: "food_license", label: "Food License" },
  { value: "mpcb_consent", label: "MPCB Consent" },
  { value: "midc_allotment", label: "MIDC Allotment" },
  { value: "dish_factory_license", label: "DISH Factory License" },
  { value: "fire_noc", label: "Fire NOC" },
];

function App() {
  const [file, setFile] = useState(null);
  const [docType, setDocType] = useState("generic");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  const resetOutcome = () => {
    setResult(null);
    setError(null);
  };

  const pickFile = (selected) => {
    if (!selected) return;
    setFile(selected);
    resetOutcome();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragActive(false);
    pickFile(e.dataTransfer.files[0]);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      setError("Please choose a file first.");
      return;
    }

    setLoading(true);
    resetOutcome();

    const formData = new FormData();
    formData.append("file", file);
    formData.append("doc_type", docType);

    try {
      const response = await fetch(
        "http://127.0.0.1:8000/document-validator/validate",
        { method: "POST", body: formData }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Something went wrong.");
      }

      setResult(data);
    } catch (err) {
      if (err instanceof TypeError) {
        // fetch throws a generic TypeError when the server is unreachable
        setError("Couldn't reach the backend. Is it running on port 8000?");
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    setFile(null);
    resetOutcome();
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="page">
      <div className="card">
        <h1>Document Pre-Validator</h1>
        <p className="subtitle">
          Upload a document to check it before submitting your application.
        </p>

        <form onSubmit={handleSubmit}>
          <label className="field-label" htmlFor="docType">
            Document type
          </label>
          <select
            id="docType"
            value={docType}
            onChange={(e) => setDocType(e.target.value)}
            disabled={loading}
          >
            {DOC_TYPES.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>

          <div
            className={`dropzone ${dragActive ? "dropzone-active" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              onChange={(e) => pickFile(e.target.files[0])}
              disabled={loading}
              hidden
            />
            {file ? (
              <span>📄 {file.name}</span>
            ) : (
              <span>Click to choose a file, or drag one here (PDF, PNG, JPG)</span>
            )}
          </div>

          <div className="button-row">
            <button type="submit" disabled={loading || !file}>
              {loading ? (
                <>
                  <span className="spinner" /> Checking...
                </>
              ) : (
                "Validate Document"
              )}
            </button>
            {(file || result || error) && !loading && (
              <button type="button" className="secondary" onClick={handleClear}>
                Clear
              </button>
            )}
          </div>
        </form>

        {error && <div className="alert alert-error">⚠️ {error}</div>}

        {result && (
          <div className={`alert ${result.valid ? "alert-success" : "alert-warning"}`}>
            <h3>{result.valid ? "✅ Valid" : "❌ Issues found"}</h3>
            {result.issues.length > 0 && (
              <ul>
                {result.issues.map((issue, i) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
            )}
            <details>
              <summary>Extracted text preview</summary>
              <p className="preview-text">{result.extracted_text_preview}</p>
            </details>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
