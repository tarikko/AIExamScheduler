def room_utilization_score(room_capacity: int,number_of_students: int):
    # f(capacity,students) = (4 * students * (capacity - students)) / capacity²
    # will be a smooth parabolla with peak at students = capacity / 2 (treating capacity as a constant and students as the variable)
    alpha = 0.01
    f = (4 * number_of_students * (room_capacity - number_of_students)) / (room_capacity ** 2)

    # to prevent the score from ever reaching 0 
    # so that when we use it as a penalty in denominator we dont get division by zero
    return max(alpha,f) 

def check_empty_domains(domain: list[list]):
    for d in domain:
        if len(d) == 0:
            return True
        
    return False