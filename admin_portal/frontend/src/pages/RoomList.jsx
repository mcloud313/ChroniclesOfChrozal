import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';

function RoomList() {
    const [rooms, setRooms] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get('/rooms/')
            .then(response => {
                setRooms(response.data);
                setLoading(false);    
            })
            .catch(error => {
                console.error('Error fetching rooms:', error);
                setLoading(false);
            });
    }, []);

    if (loading) return <div>Loading...</div>;

    return (
        <div className="room-list">
            <h2>Rooms</h2>
            <Link to="/rooms/new">
                <button>Create New Room</button>
            </Link>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Name</th>
                        <th>Area ID</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {rooms.map(room => (
                        <tr key={room.id}>
                            <td>{room.id}</td>
                            <td>{room.name}</td>
                            <td>{room.area_id}</td>
                            <td>
                                <Link to={`/rooms/${room.id}`}>Edit</Link>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export default RoomList;