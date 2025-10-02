import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../api';

function RoomEdit() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [room, setRoom] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get(`/rooms/${id}`)
            .then(response => {
                setRoom(response.data);
                setLoading(false);
            })
            .catch(error => {
                console.error('Error fetching room:', error);
                setLoading(false);
            });
    }, [id]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            const updateData = {
                area_id: room.area_id,
                name: room.name,
                description: room.description,
                coinage: room.coinage,
                flags: room.flags,
                spawners: room.spawners
            };
            
            await api.put(`/rooms/${id}`, updateData);
            alert('Room updated Succesfully!');
            navigate('/rooms');
        } catch (error) {
            console.error('Error updating room:', error);
            alert('Failed to update room');
        }
    };

        if (loading) return <div>Loading...</div>;
        if (!room) return <div>Room not found</div>;

        return (
            <div className="room-edit">
                <h2>Edit Room {id}</h2>
                <form onSubmit={handleSubmit}>
                    <label>
                        Name:
                        <input
                        type="text"
                        value={room.name}
                        onChange={(e) => setRoom({...room, name: e.target.value})}
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
                        Area ID:
                        <input
                        type="number"
                        value={room.area_id}
                        onChange={(e) => setRoom({...room, area_id: parseInt(e.target.value)})}
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

                    <button type="submit">Save Changes</button>
                    <button type="button" onClick={() => navigate('/rooms')}>Cancel</button>
                </form>
            </div>
        );
    }

    export default RoomEdit;
