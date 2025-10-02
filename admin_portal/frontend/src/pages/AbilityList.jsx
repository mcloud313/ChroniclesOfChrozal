import { useState, useEffect } from 'react';
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
            <h2>Abilities</h2>
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
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export default AbilityList;