import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import RoomList from './pages/RoomList';
import RoomEdit from './pages/RoomEdit';
import AbilityList from './pages/AbilityList';
import './App.css';

function App() {
  return (
    <Router>
      <div className="app">
        <nav className="navbar">
          <h1>Chrozal Admin Portal</h1>
          <div className="nav-links">
            <Link to="/rooms">Rooms</Link>
            <Link to="/abilities">Abilities</Link>
          </div>
        </nav>

        <div className="content">
          <routes>
            <Route path="/" element={<h2>Welcome to Chrozal Admin</h2>} />
            <Route path="/rooms" element={<RoomsList />} />
            <Route path="/rooms/:id" element={<RoomEdit />} />
            <Route path="/abilities" element={<AbilityList />} />
          </routes>
        </div>
      </div>
    </Router>
  );
}

export default App;