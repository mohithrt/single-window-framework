import { useState } from "react";

function App() {
  const [file, setFile] = useState(null);
  const [docType, setDocType] = useState("generic");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      setError("Please choose a file first.");
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("doc_type", docType);

    try {
      const response = await fetch(
        "http://127.0.0.1:8000/document-validator/validate",
        {
          method: "POST",
          body: formData,
        }
      );

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Something went wrong");
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 480, margin: "40px auto", fontFamily: "sans-serif" }}>
      <h1>Document Pre-Validator</h1>
      <p>Upload a document to check it before submitting your application.</p>

      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 12 }}>
          <label>Document type: </label>
          <select value={docType} onChange={(e) => setDocType(e.target.value)}>
            <option value="generic">Generic</option>
            <option value="gst_certificate">GST Certificate</option>
            <option value="pan_card">PAN Card</option>
            <option value="udyam_registration">Udyam Registration</option>
            <option value="mca21_incorporation">MCA21 Incorporation</option>
            <option value="food_license">Food License</option>
            <option value="mpcb_consent">MPCB Consent</option>
            <option value="midc_allotment">MIDC Allotment</option>
            <option value="dish_factory_license">DISH Factory License</option>
            <option value="fire_noc">Fire NOC</option>
          </select>
        </div>

        <div style={{ marginBottom: 12 }}>
          <input
            type="file"
            onChange={(e) => setFile(e.target.files[0])}
          />
        </div>

        <button type="submit" disabled={loading}>
          {loading ? "Checking..." : "Validate Document"}
        </button>
      </form>

      {error && (
        <p style={{ color: "red", marginTop: 16 }}>Error: {error}</p>
      )}

      {result && (
        <div style={{ marginTop: 24, padding: 16, border: "1px solid #ccc" }}>
          <h3 style={{ color: result.valid ? "green" : "red" }}>
            {result.valid ? "✅ Valid" : "❌ Issues found"}
          </h3>
          {result.issues.length > 0 && (
            <ul>
              {result.issues.map((issue, i) => (
                <li key={i}>{issue}</li>
              ))}
            </ul>
          )}
          <p style={{ fontSize: 12, color: "#666" }}>
            Extracted text preview: {result.extracted_text_preview}
          </p>
        </div>
      )}
    </div>
  );
}

export default App;
