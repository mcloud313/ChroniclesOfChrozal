import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';

function RoomCreate() {
    const navigate = useNavigate();
    const [areas, setAreas] = useState([]);
    const [room, setRoom] = useState({
        area_id: 1,
        name: '',
        description: 'You see nothing special.',
        coinage: 0,
        flags: [],
        spawners: {}
    });
    
    useEffect(() => {
        api.get('/areas/')
        .then(response => setAreas(response.data))
        .catch(error => console.error('Error fetching areas:', error));
    }, []);

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            await api.post('/rooms', room);
            alert('Room created successfully!');
            navigate('rooms');
        } catch (error) {
            console.error('Error creating room:', error);
            alert('Failed to create room');
        }
    };

    return (
        <div className="room-create">
            <h2>Create a New Room</h2>
            <form onSubmit={handleSubmit}>
                <label>
                    Area:
                    <select
                        value={room.area_id}
                        onChange={(e) => setRoom({...room, area_id: parseInt(e.target.value)})}
                        >
                            {areas.map(area => (
                                <option key={area.id} value={area.id}>
                                    {area.name}
                                </option>
                            ))}
                        </select>
                </label>

                <label>
                    Name:
                    <input
                        type="text"
                        value={room.name}
                        onChange={(e) => setRoom({...room, name: e.target.value})}
                        required
                        />
                </label>

                <label>
                    Description:
                    <textarea
                        value={room.description}
                        onChange={(e) => setRoom({...room, description: e.target.value})}
                        rows={4}
                        />
                </label>

                <label>
                    Coinage:
                    <input
                        type="number"
                        value={room.coinage}
                        onChange={(e) => setRoom({...room, coinage: parseInt(e.target.value)})}
                        />
                </label>

                <button type="submit">Create Room</button>
                <button type="button" onClick={() => navigate('/rooms')}>Cancel</button>
            </form>
        </div>
    );
}

export default RoomCreate;