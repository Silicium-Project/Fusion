#pragma once

namespace splitter {

template <typename K, typename V>
FlatMap<K, V>::FlatMap(std::initializer_list<value_type> init) {
    insert(init.begin(), init.end());
}

template <typename K, typename V>
FlatMap<K, V>& FlatMap<K, V>::operator=(std::initializer_list<value_type> init) {
    data_.clear();
    insert(init.begin(), init.end());
    return *this;
}

template <typename K, typename V>
bool FlatMap<K, V>::insert(const K& key, const V& value) {
    return insert_impl(key, value);
}

template <typename K, typename V>
bool FlatMap<K, V>::insert(K&& key, V&& value) {
    return insert_impl(std::move(key), std::move(value));
}

template <typename K, typename V>
template <typename InputIt>
void FlatMap<K, V>::insert(InputIt first, InputIt last) {
    for (; first != last; ++first)
        insert(first->first, first->second);
}

template <typename K, typename V>
typename FlatMap<K, V>::iterator FlatMap<K, V>::find(const K& key) {
    auto it = lower_bound(key);
    if (it != data_.end() && it->first == key)
        return it;
    return data_.end();
}

template <typename K, typename V>
typename FlatMap<K, V>::const_iterator FlatMap<K, V>::find(const K& key) const {
    auto it = lower_bound(key);
    if (it != data_.end() && it->first == key)
        return it;
    return data_.end();
}

template <typename K, typename V>
bool FlatMap<K, V>::contains(const K& key) const {
    return find(key) != data_.end();
}

template <typename K, typename V>
V& FlatMap<K, V>::operator[](const K& key) {
    auto it = lower_bound(key);
    if (it == data_.end() || it->first != key)
        it = data_.insert(it, {key, V{}});
    return it->second;
}

template <typename K, typename V>
const V& FlatMap<K, V>::at(const K& key) const {
    auto it = find(key);
    if (it == data_.end())
        throw std::out_of_range("FlatMap::at");
    return it->second;
}

template <typename K, typename V>
typename FlatMap<K, V>::iterator FlatMap<K, V>::begin() noexcept {
    return data_.begin();
}

template <typename K, typename V>
typename FlatMap<K, V>::const_iterator FlatMap<K, V>::begin() const noexcept {
    return data_.begin();
}

template <typename K, typename V>
typename FlatMap<K, V>::iterator FlatMap<K, V>::end() noexcept {
    return data_.end();
}

template <typename K, typename V>
typename FlatMap<K, V>::const_iterator FlatMap<K, V>::end() const noexcept {
    return data_.end();
}

template <typename K, typename V>
std::size_t FlatMap<K, V>::size() const noexcept {
    return data_.size();
}

template <typename K, typename V>
bool FlatMap<K, V>::empty() const noexcept {
    return data_.empty();
}

template <typename K, typename V>
const typename FlatMap<K, V>::container_type& FlatMap<K, V>::values() const noexcept {
    return data_;
}

template <typename K, typename V>
void FlatMap<K, V>::clear() noexcept {
    data_.clear();
}

template <typename K, typename V>
typename FlatMap<K, V>::iterator FlatMap<K, V>::lower_bound(const K& key) {
    return std::lower_bound(data_.begin(), data_.end(), key,
                            [](const value_type& kv, const K& k) { return kv.first < k; });
}

template <typename K, typename V>
typename FlatMap<K, V>::const_iterator FlatMap<K, V>::lower_bound(const K& key) const {
    return std::lower_bound(data_.begin(), data_.end(), key,
                            [](const value_type& kv, const K& k) { return kv.first < k; });
}

template <typename K, typename V>
template <typename KeyT, typename ValueT>
bool FlatMap<K, V>::insert_impl(KeyT&& key, ValueT&& value) {
    auto it = lower_bound(key);
    if (it != data_.end() && it->first == key)
        return false;
    data_.insert(it, {std::forward<KeyT>(key), std::forward<ValueT>(value)});
    return true;
}

}  // namespace splitter
