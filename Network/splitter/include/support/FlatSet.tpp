#pragma once

#include <algorithm>
#include <utility>

namespace splitter {

template <typename T>
FlatSet<T>::FlatSet(std::initializer_list<T> init) {
    insert(init.begin(), init.end());
}

template <typename T>
FlatSet<T>& FlatSet<T>::operator=(std::initializer_list<T> init) {
    values_.clear();
    insert(init.begin(), init.end());
    return *this;
}

template <typename T>
bool FlatSet<T>::insert(const T& value) {
    auto size_before = values_.size();
    insert_with_hint(value);
    return values_.size() != size_before;
}

template <typename T>
bool FlatSet<T>::insert(T&& value) {
    auto size_before = values_.size();
    insert_with_hint(std::move(value));
    return values_.size() != size_before;
}

template <typename T>
bool FlatSet<T>::insert(std::string_view value) {
    if constexpr (std::is_same_v<T, std::string>)
        return insert(std::string(value));
    else
        return insert(T(value));
}

template <typename T>
typename FlatSet<T>::iterator FlatSet<T>::insert(const_iterator, const T& value) {
    return insert_with_hint(value);
}

template <typename T>
typename FlatSet<T>::iterator FlatSet<T>::insert(const_iterator, T&& value) {
    return insert_with_hint(std::move(value));
}

template <typename T>
typename FlatSet<T>::iterator FlatSet<T>::insert(iterator, const T& value) {
    return insert_with_hint(value);
}

template <typename T>
typename FlatSet<T>::iterator FlatSet<T>::insert(iterator, T&& value) {
    return insert_with_hint(std::move(value));
}

template <typename T>
template <typename InputIt>
void FlatSet<T>::insert(InputIt first, InputIt last) {
    for (; first != last; ++first)
        insert(*first);
}

template <typename T>
template <typename U>
bool FlatSet<T>::contains(const U& value) const {
    return std::binary_search(values_.begin(), values_.end(), value);
}

template <typename T>
typename FlatSet<T>::iterator FlatSet<T>::begin() noexcept {
    return values_.begin();
}

template <typename T>
typename FlatSet<T>::const_iterator FlatSet<T>::begin() const noexcept {
    return values_.begin();
}

template <typename T>
typename FlatSet<T>::iterator FlatSet<T>::end() noexcept {
    return values_.end();
}

template <typename T>
typename FlatSet<T>::const_iterator FlatSet<T>::end() const noexcept {
    return values_.end();
}

template <typename T>
bool FlatSet<T>::empty() const noexcept {
    return values_.empty();
}

template <typename T>
std::size_t FlatSet<T>::size() const noexcept {
    return values_.size();
}

template <typename T>
void FlatSet<T>::clear() noexcept {
    values_.clear();
}

template <typename T>
const typename FlatSet<T>::container_type& FlatSet<T>::values() const noexcept {
    return values_;
}

template <typename T>
void FlatSet<T>::merge(const FlatSet<T>& other) {
    insert(other.begin(), other.end());
}

template <typename T>
typename FlatSet<T>::iterator FlatSet<T>::insert_with_hint(const T& value) {
    auto it = std::lower_bound(values_.begin(), values_.end(), value);
    if (it != values_.end() && *it == value)
        return it;
    return values_.insert(it, value);
}

template <typename T>
typename FlatSet<T>::iterator FlatSet<T>::insert_with_hint(T&& value) {
    auto it = std::lower_bound(values_.begin(), values_.end(), value);
    if (it != values_.end() && *it == value)
        return it;
    return values_.insert(it, std::move(value));
}

}  // namespace splitter
