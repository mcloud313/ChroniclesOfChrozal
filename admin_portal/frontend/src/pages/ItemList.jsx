import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';

function ItemList() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get('/items/')
        .then(response => {
            setItems(response.data);
            setLoading(false);
        })
        .catch(error => {
            console.error('Error fetching items:', error);
            setLoading(false);
        });
    }, []);

    if (loading) return <div className="loading">Loading...</div>;

    return (
        <div className="item-list">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                <h2>Item Templates</h2>
                <Link to="/items/new">
                    <button>Create New Item</button>
                </Link>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Name</th>
                        <th>Type</th>
                        <th>Value</th>
                        <th>Weight</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {items.map(item => (
                        <tr key={item.id}>
                            <td>{item.id}</td>
                            <td>{item.name}</td>
                            <td>{item.item_type}{item.subtype ? ` (${item.subtype})` : ''}</td>
                            <td>{item.value}</td>
                            <td>{item.weight}</td>
                            <td>
                                <Link to={`/items/${item.id}`}>Edit</Link>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export default ItemList;