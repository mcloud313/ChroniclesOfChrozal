import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom'
import api from '../api';

function AbilityList() {
    const [abilities, setAbilities] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get('/abilities/')
            .then(response => {
                setAbilities(response.data);
                setLoading(false);
            })
            .catch(error => {
                console.error('Error fetching abilities', error);
                setLoading(false);
            });
    }, []);

    if (loading) return <div>Loading...</div>;

    return (
        <div className="ability-list">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h2>Abilities</h2>
                <Link to="/abilities/new">
                <button>Create New Ability</button>
                </Link>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Name</th>
                            <th>Type</th>
                            <th>Level Req</th>
                            <th>Cost</th>
                        </tr>
                    </thead>
                    <tbody>
                    {abilities.map(ability => (
                        <tr key={ability.id}>
                            <td>{ability.id}</td>
                            <td>{ability.name}</td>
                            <td>{ability.ability_type}</td>
                            <td>{ability.level_req}</td>
                            <td>{ability.cost}</td>
                            <td>
                                <Link to={`/abilities/${ability.id}`}>Edit</Link>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export default AbilityList;