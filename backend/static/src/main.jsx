import React from 'https://esm.sh/react@18';
import ReactDOM from 'https://esm.sh/react-dom@18';

function App() {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/v1/hello');
      const json = await response.json();
      setData(json.message);
    } catch (error) {
      console.error("Error fetching data:", error);
      setData("Failed to fetch data from backend.");
    } finally {
      setLoading(false);
    }
  };

  return React.createElement(
    'div',
    { style: { fontFamily: 'Arial', margin: '40px' } },
    [
      React.createElement('h2', { key: 'title' }, 'Modular React + Flask'),
      React.createElement('p', { key: 'desc' }, 'Loaded via a separate main.jsx file!'),
      React.createElement(
        'button',
        { 
          key: 'btn', 
          onClick: fetchData,
          style: { padding: '8px 16px', cursor: 'pointer' }
        },
        loading ? 'Fetching...' : 'Call /api/v1/hello'
      ),
      data && React.createElement(
        'div',
        { key: 'res', style: { marginTop: '20px', background: '#eee', padding: '10px' } },
        `Backend Response: ${data}`
      )
    ]
  );
}

// Mount to the root div
const rootElement = document.getElementById('root');
const root = ReactDOM.createRoot(rootElement);
root.render(React.createElement(App));