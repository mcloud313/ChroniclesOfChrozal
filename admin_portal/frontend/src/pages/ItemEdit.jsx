import { useState, useEffect } from 'react';
import { useParams, useNavigate } from  'react-router-dom';
import api from '../api';

function ItemEdit() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [item, setItem] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get(`/items/${id}`)
            .then(response =>  {
                setItem(response.data);
                setLoading(false);
            })
            .catch(error => {
                console.error('Error fetching item:', error);
                setLoading(false);
            });
    }, [id]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            const updateData = {
                name: item.name,
                description: item.description,
                item_type: item.item_type,
                subtype: item.subtype,
                value: item.value,
                weight: item.weight,
                max_stack: item.max_stack,
                equip_slot: item.equip_slot,
                stats: item.stats,
                flags: item.flags,
                damage: item.damage,
                armor: item.armor,
                consumable_effect: item.consumable_effect
            };

            await api.put(`/items/${id}`, updateData);
            alert('Item updated successfully!');
            navigate('/items');
        } catch (error) {
            console.error('Error updating item:', error);
            alert('Failed to update item');
        }
    };

    if (loading) return <div className="loading">Loading...</div>;
    if (!item) return <div className="error">Item not found</div>;

    return (
        <div className="item-edit">
            <h2>Edit Item: {item.name}</h2>
            <form onSubmit={handleSubmit}>
                <label>
                    Name:
                    <input
                    type="text"
                    value={item.name}
                    onChange={(e) => setItem({...item, name: e.target.value})}
                    required
                    />
                </label>

                <label>
                    Description:
                    <textarea
                    value={item.description}
                    onChange={(e) => setItem({...item, description: e.target.value})}
                    rows={3}
                    />
                </label>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                    <label>
                        Item Type:
                        <select
                        value={item.item_type}
                        onChange={(e) => setItem({...item, item_type: e.target.value})}
                        >
                        <option value="WEAPON">Weapon</option>
                        <option value="RANGED_WEAPON">Ranged Weapon</option>
                        <option value="TWO_HANDED_WEAPON">Two-Handed Weapon</option>
                        <option value="ARMOR">Armor</option>
                        <option value="CONSUMABLE">Consumable</option>
                        <option value="QUEST_ITEM">Quest Item</option>
                        <option value="MISC">Miscellaneous</option>
                    </select>
                    </label>

                    <label>
                        Subtype:
                        <input
                        type="text"
                        value={item.subtype || ''}
                        onChange={(e) => setItem({...item, subtype: e.target.value})}
                        /> 
                    </label>

                    <label>
                        Value:
                        <input
                        type="number"
                        value={item.value}
                        onChange={(e) => setItem({...item, value: parseInt(e.target.value)})}
                        />
                    </label>

                    <label>
                        Weight:
                        <input
                        type="number"
                        step="0.1"
                        value={item.weight}
                        onChange={(e) => setItem({...item, weight: parseFloat(e.target.value)})}
                        />
                    </label>

                    <label>
                        Max Stack:
                        <input 
                        type="number"
                        value={item.max_stack}
                        onChange={(e) => setItem({...item, max_stack: parseInt(e.target.value)})}
                        />
                    </label>

                    <label>
                        Equip Slot:
                        <select
                        value={item.equip_slot || ''}
                        onChange={(e) => setItem({...item, equip_slot: e.target.value})}
                        >
                        <option value="">None</option>
                        <option value="head">Head</option>
                        <option value="body">Body</option>
                        <option value="hands">Hands</option>
                        <option value="legs">Legs</option>
                        <option value="feet">Feet</option>
                        <option value="main_hand">Main Hand</option>
                        <option value="off_hand">Off Hand</option>
                        <option value="both_hands">Both Hands</option>
                        <option value="neck">Neck</option>
                        <option value="finger">Finger</option>
                        </select>
                    </label>
                </div>

                <button type="submit">Save Changes</button>
                <button type="button" onClick={() => navigate('/items')}>Cancel</button>
            </form>
        </div>
    );
}

export default ItemEdit;