import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';

function MobList() {
    const [mobs, setMobs] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() =>  {
        api.get('/mobs/')
            .then(response => {
                setMobs(response.data);
                setLoading(false);
            })
            .catch(error => {
                console.error('Error fetching mobs:', error);
                setLoading(false);
            });
    }, []);

    if (loading) return <div className="loading">Loading...</div>

    return (
        <div className="mob-list">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h2>Mob Templates</h2>
                <Link to="/mobs/new">
                    <button>Create New Mob</button>
                </Link>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Name</th>
                        <th>Type</th>
                        <th>Level</th>
                        <th>HP</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {mobs.map(mob => (
                        <tr key={mob.id}>
                            <td>{mob.id}</td>
                            <td>{mob.name}</td>
                            <td>{mob.mob_type || 'N/A'}</td>
                            <td>{mob.level}</td>
                            <td>{mob.max_hp}</td>
                            <td>
                                <Link to={`/mobs/${mob.id}`}>Edit</Link>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export default MobList;