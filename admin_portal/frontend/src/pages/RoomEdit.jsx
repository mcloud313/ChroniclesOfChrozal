import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../api';

function RoomEdit() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [room, setRoom] = useState(null);
    const [loading, setLoading] = useState(true);
    const [showExitForm, setShowExitForm] = useState(false);
    const [newExit, setNewExit] = useState({
        direction: 'north',
        destination_room_id: '',
        is_hidden: false,
        create_reverse: true,
        has_door: false,
        door_name: '',
        is_locked: false,
        lock_difficulty: 0,
        required_key_id: null,
        is_trapped: false,
        trap_difficulty: 0,
        trap_damage: 0
    });

    const directions = ['north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest', 'up', 'down'];

    useEffect(() => {
        Promise.all([
            api.get(`/rooms/${id}`),
            api.get(`/rooms/${id}/exits`)
        ])
          .then(([roomResponse, exitsResponse]) => {
            setRoom(roomResponse.data);
            setExits(exitsResponse.data);
            setLoading(false);
          })
          .catch(error => {
            console.error('Error fetching room data:', error);
            setLoading(false);
          });
    }, [id]);

    const buildExitDetails = () => {
        const details = {};

        if (newExit.has_door) {
            details.door = {
                name: newExit.door_name || 'door',
                is_locked: newExit.is_locked
            };

            if (newExit.is_locked) {
                details.door.lock_difficulty = newExit.lock_difficulty;
                if (newExit.required_key_id) {
                    details.door.required_key_id = newExit.required_key_id;
                }
            }
        }

        if (newExit.is_trapped) {
            details.trap = {
                difficulty: newExit.trap_difficulty,
                damage: newExit.trap_damage,
                damage_type: 'physical'
            };
        }

        return details;
    }

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

    const handleCreateExit = async (e) => {
        e.preventDefault();
        try {
            const exitData = {
                direction: newExit.direction,
                destination_room_id: newExit.destination_room_id,
                is_hidden: newExit.is_hidden,
                create_reverse: newExit.create_reverse,
                details: buildExitDetails()
            };
            await api.post(`/rooms/${id}/exits`, newExit, exitData);
            //Reload exits
            const exitsResponse = await api.get(`/rooms/${id}/exits`);
            setExits(exitsResponse.data);
            setShowExitForm(false);
            setNewExit({
                direction: 'north',
                destination_room_id: '',
                is_hidden: false,
                create_reverse: true
            });
            alert('Exit created successfully!');
        } catch (error) {
            console.error('Error creating exit:', error);
            alert('Failed to create exit: ' + (error.response?.data?.detail || error.message));
        }
    };

    const handleDeleteExit = async (exitId, deleteReverse = false) => {
        if (!confirm('Are you sure you want to delete this exit?')) return;

        try {
            await api.delete(`/rooms/exits/${exitId}`, {
                params: { delete_reverse: deleteReverse }
            });
            setExits(exits.filter(e => e.id !== exitId));
            alert('Exit deleted successfully!');
        } catch (error) {
            console.error('Error deleting exit:', error);
            alert('Failed to delete exit');
        }
    };

        if (loading) return <div>Loading...</div>;
        if (!room) return <div>Room not found</div>;

        return (
            <div className="room-edit">
                <h2>Edit Room {id}: {room.name}</h2>
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

                <div style={{ marginTop: '2rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                        <h3>Exits ({exits.length})</h3>
                        <button type="button" onClick={() => setShowExitForm(!showExitForm)}>
                            {showExitForm ? 'Cancel' : 'Add Exit'}
                        </button>
                    </div>

                    {showExitForm && (
                        <form onSubmit={handleCreateExit} style={{ background: '#d9c7a8', padding: '1rem', borderRadius: '4px', marginTop: '1rem'}}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                <label>
                                    Direction:
                                    <select
                                        value={newExit.direction}
                                        onChange={(e) => setNewExit({...newExit, direction: e.target.value})}
                                    >
                                        {directions.map(dir => (
                                            <option key={dir} value={dir}>{dir}</option>
                                        ))}
                                    </select>
                                </label>

                                <label>
                                    Destination Room ID:
                                    <input
                                    type="number"
                                    value={newExit.destination_room_id}
                                    onChange={(e) => setNewExit({...newExit, destination_room_id: parseInt(e.target.value)})}
                                    required
                                    />
                                </label>

                                <label style={{ flexDirection: 'row', gap: '0.5rem', cursor: 'pointer '}}>
                                    <input
                                    type="checkbox"
                                    checked={newExit.create_reverse}
                                    onChange={(e) => setNewExit({...newExit, create_reverse: e.target.checked})}
                                    />
                                    Create reverse exit automatically
                                </label>

                            </div>

                                <label style={{ flexDirection: 'row', gap: '0.5rem', cursor: 'pointer' }}>
                                    <input
                                    type="checkbox"
                                    checked={newExit.is_hidden}
                                    onChange={(e) => setNewExit({...newExit, is_hidden: e.target.checked})}
                                    />
                                    Hidden Exit
                                </label>

                                <label style={{ flexDirection: 'row', gap: '0.5rem', cursor: 'pointer' }}>
                                    <input
                                    type="checkbox"
                                    checked={newExit.has_door}
                                    onChange={(e) => setNewExit({...newExit, has_door: e.target.checked})}
                                    />
                                    Has a Door
                                </label>

                                {newExit.has_door && (
                                    <div style={{ marginLeft: '2rem', padding: '1rem', background: '#e8dcc4', borderRadius: '4px'}}>
                                        <label>
                                            Door Name:
                                            <input
                                            type="text"
                                            value={newExit.door_name}
                                            onChange={(e) => setNewExit({...newExit, door_name: e.target.value})}
                                            placeholder="door, gate, hatch etc."
                                            />
                                        </label>

                                        <label style={{ flexDirection: 'row', gap: '0.5rem', cursor: 'pointer '}}>
                                            <input
                                            type="checkbox"
                                            checked={newExit.is_locked}
                                            onChange={(e) => setNewExit({...newExit, is_locked: e.target.checked})}
                                            />
                                            Locked
                                        </label>

                                        {newExit.is_locked && (
                                            <>
                                            <label>
                                                Lock Difficulty (DC):
                                                <input
                                                type="number"
                                                value={newExit.lock_difficulty}
                                                onChange={(e) => setNewExit({...newExit, lock_difficulty: parseInt(e.target.value)})}
                                                min="0"
                                                max="50"
                                                />
                                            </label>

                                            <label>
                                                Required Key Item ID (Optional):
                                                <input
                                                type="number"
                                                value={newExit.required_key_id || ''}
                                                onChange={(e) => setNewExit({...newExit, required_key_id: parseInt(e.target.value) || null})}
                                                placeholder="Leaqve empty for a pickable lock"
                                                />
                                            </label>
                                            </>
                                        )}
                                    </div>
                                )}

                                <label style={{ flexDirection: 'row', gap: '0.5rem', cursor: 'pointer' }}>
                                    <input
                                    type="checkbox"
                                    checked={newExit.is_trapped}
                                    onChange={(e) => setNewExit({...newExit, is_trapped: e.target.checked})}
                                    />
                                    Trapped
                                </label>

                                {newExit.is_trapped && (
                                    <div style={{ marginLeft: '2rem', padding: '1rem', background: '#e8dcc4', borderRadius: '4px' }}>
                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                        <label>
                                            Trap Detection DC:
                                            <input
                                            type="number"
                                            value={newExit.trap_difficulty}
                                            onChange={(e) => setNewExit({...newExit, trap_difficulty: parseInt(e.target.value)})}
                                            min="0"
                                            max="50"
                                            />
                                        </label>

                                        <label>
                                            Trap Damage:
                                            <input
                                            type="number"
                                            value={newExit.trap_damage}
                                            onChange={(e) => setNewExit({...newExit, trap_damage: parseInt(e.target.value)})}
                                            min="0"
                                            />
                                        </label>
                                    </div>
                                    </div>
                                )}
                                <button type="submit">Create Exit</button>
                        </form>
                    )}

                    {exits.length > 0 ? (
                        <table style={{ marginTop: '1rem' }}>
                            <thead>
                                <tr>
                                    <th>Direction</th>
                                    <th>Destination</th>
                                    <th>Hidden</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {exits.map(exit => (
                                    <tr key={exit.id}>
                                        <td>{exit.direction}</td>
                                        <td>Room {exit.destination_room_id}</td>
                                        <td>{exit.is_hidden ? 'Yes' : 'No'}</td>
                                        <td>
                                            <button
                                            type="button"
                                            onClick={() => handleDeleteExit(exit.id, false)}
                                            style={{ marginRight: '0.5rem' }}
                                            >
                                                Delete
                                            </button>
                                            <button 
                                            type="button"
                                            onClick={() => handleDeleteExit(exit.id, true)}
                                            >
                                            Delete Both
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    ) : (
                        <p style={{ marginTop: '1rem', color: '#6b5537' }}> No exits yet. Add one to connect to this room.</p>
                    )}
                </div>
            </div>
        );
    }

    export default RoomEdit;
